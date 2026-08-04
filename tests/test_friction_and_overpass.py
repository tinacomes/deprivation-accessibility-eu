"""Tier-1 fast path: friction-surface cost distance and Overpass parsing."""

import numpy as np
import pandas as pd
import pytest

from depacc.ingest.overpass import _parse_elements, build_query

scipy = pytest.importorskip("scipy")

from depacc.access.friction import cost_distance_times  # noqa: E402


def test_uniform_friction_matches_straight_line():
    """On a uniform surface, time to an axis-aligned pixel = distance x friction."""
    f = np.full((21, 21), 0.01)  # minutes per metre
    dx = np.full(21, 1000.0)     # 1 km pixels
    t = cost_distance_times(f, [(10, 10)], dx, 1000.0, max_time_min=1000.0)[0]
    assert t[10, 10] == 0.0
    assert t[10, 15] == pytest.approx(5 * 1000 * 0.01)   # 5 px east = 50 min
    assert t[5, 10] == pytest.approx(5 * 1000 * 0.01)    # 5 px north
    # Diagonal uses sqrt(2) edges, cheaper than the manhattan route.
    assert t[15, 15] == pytest.approx(5 * np.sqrt(2) * 1000 * 0.01, rel=1e-6)


def test_barrier_forces_detour_and_cutoff():
    f = np.full((11, 11), 0.01)
    f[:10, 5] = np.nan  # impassable wall with a gap at the bottom row
    dx = np.full(11, 1000.0)
    t = cost_distance_times(f, [(5, 2)], dx, 1000.0, max_time_min=1000.0)[0]
    direct = 6 * 1000 * 0.01
    assert t[5, 8] > direct  # detour around the wall
    assert np.isfinite(t[5, 8])
    # Tight cutoff renders the far side unreachable (NaN).
    t_cut = cost_distance_times(f, [(5, 2)], dx, 1000.0, max_time_min=direct)[0]
    assert np.isnan(t_cut[5, 8])


def test_latitude_dependent_pixel_width():
    """Narrower pixels (higher latitude) mean shorter east-west times."""
    f = np.full((5, 11), 0.01)
    dx_wide = np.full(5, 1000.0)
    dx_narrow = np.full(5, 500.0)
    t_wide = cost_distance_times(f, [(2, 0)], dx_wide, 1000.0, 1e6)[0]
    t_narrow = cost_distance_times(f, [(2, 0)], dx_narrow, 1000.0, 1e6)[0]
    assert t_narrow[2, 10] == pytest.approx(0.5 * t_wide[2, 10])


def test_overpass_query_and_parse():
    rules = [{"key": "amenity", "value": "hospital",
              "require": {"key": "emergency", "value": "yes"}}]
    q = build_query(rules, (53.0, 9.0, 54.0, 10.5))
    assert '["amenity"="hospital"]["emergency"="yes"]' in q
    assert "(53.0,9.0,54.0,10.5)" in q
    assert q.count("(53.0,9.0,54.0,10.5)") == 3  # node + way + relation

    elements = [
        {"type": "node", "id": 1, "lat": 53.5, "lon": 10.0,
         "tags": {"amenity": "hospital", "beds": "450"}},
        {"type": "way", "id": 2, "center": {"lat": 53.6, "lon": 10.1},
         "tags": {"amenity": "hospital", "beds": "n/a"}},
        {"type": "relation", "id": 3},  # no coordinates -> dropped
        {"type": "node", "id": 1, "lat": 53.5, "lon": 10.0},  # duplicate id
    ]
    spec = {"capacity": {"source": "beds", "tag": "beds"}}
    fac = _parse_elements(elements, spec)
    assert len(fac) == 2
    assert fac.loc[0, "capacity"] == 450.0 and not fac.loc[0, "capacity_proxy"]
    assert fac.loc[1, "capacity"] == 1.0 and bool(fac.loc[1, "capacity_proxy"])


def test_keep_k_nearest_bounds_and_selects():
    """k-nearest keeps the k lowest-time destinations per origin."""
    import pandas as pd
    from depacc.access.matrices import keep_k_nearest

    od = pd.DataFrame({
        "origin": [0, 0, 0, 0, 1, 1],
        "dest": ["a", "b", "c", "d", "e", "f"],
        "time": [30.0, 10.0, 20.0, 40.0, 5.0, 15.0],
    })
    out = keep_k_nearest(od, 2)
    o0 = set(out[out.origin == 0].dest)
    assert o0 == {"b", "c"}                     # two nearest for origin 0
    assert set(out[out.origin == 1].dest) == {"e", "f"}
    assert len(out) == 4
    # k <= 0 or empty is a no-op passthrough.
    assert keep_k_nearest(od, 0) is od


def test_overpass_sends_user_agent_and_rotates_mirrors(monkeypatch):
    """406 on the first endpoint must fall through to a working mirror, and
    every request must carry a non-default User-Agent (bare requests UA -> 406)."""
    import depacc.ingest.overpass as ov

    calls = []

    class FakeResp:
        def __init__(self, status): self.status_code = status
        def json(self): return {"elements": []}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append((url, headers.get("User-Agent") if headers else None))
        return FakeResp(406 if "overpass-api.de" in url else 200)

    monkeypatch.setattr(ov.requests, "post", fake_post)
    resp, used = ov._post_overpass("q", ov.DEFAULT_MIRRORS)
    assert used != ov.DEFAULT_MIRRORS[0]          # rotated past the 406 endpoint
    assert all("depacc" in ua for _, ua in calls)  # UA always present
    assert resp.status_code == 200


def _overpass_cache(tmp_path, city="demo", service="school",
                    retrieved=None, sidecar=True):
    """A cached extraction with an optional provenance sidecar."""
    import json

    from depacc.provenance import sidecar_path

    raw = tmp_path / "data/raw/overpass" / city
    raw.mkdir(parents=True, exist_ok=True)
    cache = raw / f"{service}.json"
    cache.write_text(json.dumps({"elements": []}))
    if sidecar:
        meta = {"url": "x", "sha256": "y"}
        if retrieved is not None:
            meta["retrieved_utc"] = retrieved
        sidecar_path(cache).write_text(json.dumps(meta))
    return cache


def _age_cfg(max_age):
    return {"sources": {"overpass": {"max_age_days": max_age}},
            "output": {"raw_root": "data/raw"}}


def test_cache_stale_by_age(tmp_path):
    """The extraction date is part of the model: a cache past max_age_days is
    stale; a fresh one, or any cache with the check disabled, is not."""
    from depacc.ingest.overpass import _cache_stale

    fresh = pd.Timestamp.now(tz="UTC").isoformat()
    old = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)).isoformat()

    cache = _overpass_cache(tmp_path, retrieved=fresh)
    assert not _cache_stale(cache, _age_cfg(10))
    assert not _cache_stale(cache, _age_cfg(None))   # null disables the check

    cache_old = _overpass_cache(tmp_path, city="demo2", retrieved=old)
    assert _cache_stale(cache_old, _age_cfg(10))
    assert not _cache_stale(cache_old, _age_cfg(None))


def test_cache_without_sidecar_is_unknown_vintage(tmp_path):
    """No sidecar (or no timestamp in it) = unknown vintage -> stale whenever
    an age limit is set — the same never-trust-unprovenanced rule as the OD
    matrices. With the check disabled it is left alone."""
    from depacc.ingest.overpass import _cache_stale

    bare = _overpass_cache(tmp_path, sidecar=False)
    assert _cache_stale(bare, _age_cfg(10))
    assert not _cache_stale(bare, _age_cfg(None))

    no_ts = _overpass_cache(tmp_path, city="demo2", retrieved=None)
    assert _cache_stale(no_ts, _age_cfg(10))


def test_any_cache_stale_scans_only_existing_services(tmp_path):
    """One old service makes the CITY stale (all services re-extract on one
    snapshot date); services with no cache yet do not."""
    from depacc.ingest.overpass import any_cache_stale

    fresh = pd.Timestamp.now(tz="UTC").isoformat()
    old = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)).isoformat()
    _overpass_cache(tmp_path, service="school", retrieved=fresh)
    cfg = _age_cfg(10)

    assert not any_cache_stale(cfg, tmp_path, "demo", ["school", "pharmacy"])
    # second service, old vintage -> the whole city is stale
    import json

    from depacc.provenance import sidecar_path
    raw = tmp_path / "data/raw/overpass/demo"
    cache = raw / "pharmacy.json"
    cache.write_text(json.dumps({"elements": []}))
    sidecar_path(cache).write_text(json.dumps({"retrieved_utc": old}))
    assert any_cache_stale(cfg, tmp_path, "demo", ["school", "pharmacy"])
    # a city with no extractions at all is not stale (nothing to distrust yet)
    assert not any_cache_stale(cfg, tmp_path, "elsewhere", ["school"])
