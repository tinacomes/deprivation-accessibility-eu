"""Config loading, deep merge, city overlay, missing-parameter guard."""

import pytest
import yaml

from depacc.config import (
    ConfigError,
    MissingParameterError,
    deep_merge,
    deprivation_spec,
    everyday_service_spec,
    load_config,
    require_params,
    service_extract_aliases,
)


def test_deep_merge_nested_override():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    override = {"a": {"y": 3}, "c": 4}
    merged = deep_merge(base, override)
    assert merged == {"a": {"x": 1, "y": 3}, "b": 1, "c": 4}
    assert base == {"a": {"x": 1, "y": 2}, "b": 1}  # inputs untouched


def test_load_defaults():
    cfg = load_config()
    assert cfg["crs"]["analysis"] == "EPSG:3035"
    assert cfg["city_definition"]["fua_size_threshold"] == 100000
    assert cfg["city_definition"]["city_sample_mode"] == "stratified"
    assert cfg["tiers"]["tier1"]["modes"] == ["walk", "car"]
    assert "transit" in cfg["tiers"]["tier2"]["modes"]
    assert set(cfg["everyday_services"]) == {
        "gp", "pharmacy", "supermarket",
        "school_primary", "school_secondary",
        "green_space_local", "green_space_district",
    }
    assert set(cfg["emergency_services"]) == {
        "emergency_dept_hospital", "ambulance_station",
    }


def test_service_extract_aliases():
    cfg = load_config()
    assert service_extract_aliases(cfg) == {
        "school_secondary": "school_primary",
        "green_space_district": "green_space_local",
    }


def test_everyday_service_spec_uniform_vs_per_service():
    cfg = load_config()
    # Default is uniform: every service uses the base t0.
    assert cfg["deprivation"]["everyday"]["threshold_mode"] == "uniform"
    base_t0 = cfg["deprivation"]["everyday"]["params"]["t0"]
    for svc in ("gp", "pharmacy", "school_secondary"):
        assert everyday_service_spec(cfg, svc)["params"]["t0"] == base_t0

    # Switch to per_service: listed services override t0/k, unlisted fall back.
    cfg["deprivation"]["everyday"]["threshold_mode"] = "per_service"
    assert everyday_service_spec(cfg, "pharmacy")["params"]["t0"] == 8.0
    assert everyday_service_spec(cfg, "gp")["params"]["t0"] == 18.0
    assert (everyday_service_spec(cfg, "school_secondary")["params"]["t0"]
            > everyday_service_spec(cfg, "school_primary")["params"]["t0"])
    # form/kind preserved from the base spec.
    assert everyday_service_spec(cfg, "pharmacy")["form"] == "logistic"


def test_city_overlay_hamburg():
    cfg = load_config("hamburg")
    assert cfg["city"]["fua_code"] == "DE002F"
    assert cfg["crs"]["local"] == "EPSG:32632"
    assert cfg["crs"]["analysis"] == "EPSG:3035"  # global key survives merge
    # Hamburg uses the friction fast path (walk/car) by default; the r5
    # transit deep-dive is a documented config switch.
    assert cfg["routing"]["engine"] == "friction"
    assert cfg["routing"]["modes"] == ["walk", "car"]
    assert cfg["routing"]["max_time_min"] == 120  # inherited default


def test_every_city_declares_its_routing_engine():
    """A city config that omits `routing.engine` inherits `r5` from the
    defaults, which is the most expensive path the pipeline has — and it does so
    silently. Köln omitted it, so run 30476375657 spent over an hour rebuilding
    a *baseline* with forward R5 routing before the cross-check it was
    dispatched for could even start. The engine is a per-city cost decision and
    every real city must state it."""
    from depacc.config import CONFIG_DIR

    cities = [p.stem for p in sorted((CONFIG_DIR / "cities").glob("*.yaml"))
              if p.stem != "demo"]
    assert cities, "no city configs found"
    for city in cities:
        raw = yaml.safe_load((CONFIG_DIR / "cities" / f"{city}.yaml").read_text())
        engine = ((raw.get("routing") or {}).get("engine"))
        assert engine, (
            f"config/cities/{city}.yaml does not declare routing.engine; it "
            f"would silently inherit '{load_config()['routing']['engine']}'")
        modes = (raw.get("routing") or {}).get("modes") or []
        if engine == "friction":
            # The friction engine raises on transit (access/friction.py), so a
            # config pairing them fails only once routing has already started.
            assert "transit" not in modes, (
                f"{city}: friction engine cannot route transit")


def test_unknown_city_raises():
    with pytest.raises(ConfigError):
        load_config("atlantis")


def test_require_params_guard():
    with pytest.raises(MissingParameterError, match="Nice Paper"):
        require_params({"params": {"beta": None}, "source": "Nice Paper (2020)"})
    with pytest.raises(MissingParameterError):
        require_params({"params": {}, "source": "s"})
    assert require_params({"params": {"beta": 0.1}, "source": "s"}) == {"beta": 0.1}


def test_deprivation_spec_lookup():
    cfg = load_config()
    assert deprivation_spec(cfg, "everyday")["kind"] == "DLF"
    assert deprivation_spec(cfg, "emergency")["kind"] == "DCF"
    alt = deprivation_spec(cfg, "everyday", alternative="everyday_box_cox")
    assert alt["form"] == "box_cox"
    with pytest.raises(ConfigError):
        deprivation_spec(cfg, "sometimes")
    with pytest.raises(ConfigError):
        deprivation_spec(cfg, "everyday", alternative="nope")
