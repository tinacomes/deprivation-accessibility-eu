"""Per-(service, mode) OD-matrix selection: only route the modes a service's
regime consumes, plus the sensitivity Layer-3 accessibility modes for everyday
services (only when opted in), intersected with the modes the run can route."""

from depacc.access.matrices import (
    _route_sensitivity_modes,
    _service_modes,
    _sensitivity_access_modes,
)


def _cfg(sens_modes=None, route_sens=True, everyday_modes=None):
    cfg = {
        "everyday_services": {"gp": {}, "pharmacy": {}},
        "emergency_services": {"hospital": {}, "ambulance": {}},
        "regimes": {
            "everyday": {"modes": ["walk"]},
            "emergency": {"modes": ["car"]},
        },
        # Layer-3 extra-mode routing is opt-in; the routing tests below exercise
        # the enabled path, so default the gate on here.
        "routing": {"route_sensitivity_modes": route_sens},
    }
    axis = {}
    if sens_modes is not None:
        axis["mode"] = sens_modes
    if everyday_modes is not None:
        axis["everyday_modes"] = everyday_modes
    if axis:
        cfg["sensitivity"] = {"accessibility": axis}
    return cfg


def test_regime_modes_only_when_no_sensitivity_axis():
    # No walk_transit in the axis -> everyday=walk only, emergency=car only.
    sm = _service_modes(_cfg(sens_modes=["walk"]), available=["walk", "car"])
    assert sm["gp"] == ["walk"]
    assert sm["pharmacy"] == ["walk"]
    assert sm["hospital"] == ["car"]
    assert sm["ambulance"] == ["car"]


def test_walk_transit_axis_adds_transit_to_everyday_only():
    sm = _service_modes(_cfg(sens_modes=["walk", "walk_transit"]),
                        available=["walk", "car", "transit"])
    # Everyday services gain transit (Layer-3 reuse); order follows `available`.
    assert sm["gp"] == ["walk", "transit"]
    # Emergency services are never swept on mode.
    assert sm["hospital"] == ["car"]


def test_transit_dropped_when_run_cannot_route_it():
    # Tier-1 walk/car run: the walk_transit axis must not add transit.
    sm = _service_modes(_cfg(sens_modes=["walk", "walk_transit"]),
                        available=["walk", "car"])
    assert sm["gp"] == ["walk"]
    assert sm["hospital"] == ["car"]


def test_sensitivity_axis_alias_expansion():
    assert _sensitivity_access_modes(
        {"routing": {"route_sensitivity_modes": True},
         "sensitivity": {"accessibility": {"mode": ["walk_transit"]}}}
    ) == {"walk", "transit"}


# --- the opt-in gate (Workstream A.2 vs the Layer-3 walk+car variant) --------
def test_sensitivity_modes_gated_off_by_default():
    """Without the opt-in, the extra everyday modes are NOT routed, so a normal
    run (and the many-city batch) pays only for the regime modes."""
    cfg = _cfg(sens_modes=["walk", "walk_transit"],
               everyday_modes=[["walk"], ["walk", "car"]], route_sens=False)
    assert _sensitivity_access_modes(cfg) == set()
    sm = _service_modes(cfg, available=["walk", "car", "transit"])
    assert sm["gp"] == ["walk"]          # no transit, no car
    assert sm["hospital"] == ["car"]


def test_everyday_modes_car_routed_only_when_opted_in():
    on = _cfg(everyday_modes=[["walk"], ["walk", "car"]], route_sens=True)
    assert "car" in _sensitivity_access_modes(on)
    assert _service_modes(on, available=["walk", "car"])["gp"] == ["walk", "car"]
    off = _cfg(everyday_modes=[["walk"], ["walk", "car"]], route_sens=False)
    assert _service_modes(off, available=["walk", "car"])["gp"] == ["walk"]


def test_gate_enabled_by_env(monkeypatch):
    cfg = {"routing": {}, "sensitivity": {"accessibility": {"mode": ["walk_transit"]}}}
    assert _route_sensitivity_modes(cfg) is False
    monkeypatch.setenv("DEPACC_ROUTE_SENSITIVITY_MODES", "1")
    assert _route_sensitivity_modes(cfg) is True
    assert _sensitivity_access_modes(cfg) == {"walk", "transit"}
