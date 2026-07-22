"""Per-(service, mode) OD-matrix selection: only route the modes a service's
regime consumes, plus the sensitivity Layer-3 accessibility modes for everyday
services, intersected with the modes the run can actually route."""

from depacc.access.matrices import _service_modes, _sensitivity_access_modes


def _cfg(sens_modes=None):
    cfg = {
        "everyday_services": {"gp": {}, "pharmacy": {}},
        "emergency_services": {"hospital": {}, "ambulance": {}},
        "regimes": {
            "everyday": {"modes": ["walk"]},
            "emergency": {"modes": ["car"]},
        },
    }
    if sens_modes is not None:
        cfg["sensitivity"] = {"accessibility": {"mode": sens_modes}}
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
        {"sensitivity": {"accessibility": {"mode": ["walk_transit"]}}}
    ) == {"walk", "transit"}
