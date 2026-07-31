"""The street network and the facility source are separate decisions.

Facilities default to Overpass whatever the engine, so switching the routing
engine can never silently change the facility set (the engine cross-check and
the r5 promotion both depend on that); and an r5 city fetches the network .pbf
even when its facilities come from Overpass — before the promotion only the
engine-check's `ensure_network` did this, so a plain `depacc run` on an r5 +
Overpass city failed at the access stage with no network file.
"""

import pytest

pytest.importorskip("geopandas")

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

import depacc.ingest.boundaries as boundaries
import depacc.ingest.ghs as ghs
import depacc.ingest.osm as osm
import depacc.ingest.overpass as overpass
from depacc.ingest.pipeline import run_ingest


def _min_cfg(tmp_path, engine):
    return {
        "city": {"fua_code": "TEST1", "name": "Test", "country": "XX"},
        "routing": {"engine": engine, "modes": ["walk", "car"]},
        "everyday_services": {"gp": {}},
        "emergency_services": {},
        "sources": {},
        "output": {"root": "data/derived", "raw_root": "data/raw"},
    }


def _install_stubs(monkeypatch, tmp_path, calls):
    fua = gpd.GeoDataFrame(geometry=[box(0, 0, 1000, 1000)], crs="EPSG:3035")
    monkeypatch.setattr(boundaries, "fetch_fua_boundary", lambda cfg, root: fua)
    cells = pd.DataFrame({"cell_id": ["c0"], "x": [500.0], "y": [500.0],
                          "lon": [10.0], "lat": [53.0], "population": [10.0]})
    monkeypatch.setattr(ghs, "fetch_population_cells",
                        lambda fua, cfg, root: cells)
    fac = pd.DataFrame({"dest_id": ["gp_0"], "lon": [10.0], "lat": [53.0],
                        "x": [500.0], "y": [500.0]})
    monkeypatch.setattr(overpass, "extract_facilities_overpass",
                        lambda cfg, fua, root, city: {"gp": fac})

    src = tmp_path / "state.osm.pbf"
    src.write_bytes(b"pbf")

    def fake_fetch_pbfs(cfg, root):
        calls.append("fetch_pbfs")
        return [src]

    def fake_clip(pbf, bbox, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"clip")
        return out

    def fake_merge(clips, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"merged")
        return out

    monkeypatch.setattr(osm, "fetch_pbfs", fake_fetch_pbfs)
    monkeypatch.setattr(osm, "clip_pbf", fake_clip)
    monkeypatch.setattr(osm, "merge_pbfs", fake_merge)


def test_r5_city_with_overpass_facilities_gets_a_network(tmp_path, monkeypatch):
    calls: list = []
    _install_stubs(monkeypatch, tmp_path, calls)
    cfg = _min_cfg(tmp_path, engine="r5")
    run_ingest(cfg, "testcity", tmp_path)
    out = tmp_path / "data" / "derived" / "testcity"
    assert (out / "network_pbf_path.txt").exists()
    assert "fetch_pbfs" in calls
    # facilities still came from Overpass, not the pbf
    assert (out / "facilities_gp.parquet").exists()


def test_friction_city_never_fetches_a_network(tmp_path, monkeypatch):
    calls: list = []
    _install_stubs(monkeypatch, tmp_path, calls)
    cfg = _min_cfg(tmp_path, engine="friction")
    run_ingest(cfg, "testcity", tmp_path)
    out = tmp_path / "data" / "derived" / "testcity"
    assert not (out / "network_pbf_path.txt").exists()
    assert "fetch_pbfs" not in calls


def test_facility_source_does_not_follow_the_engine(tmp_path, monkeypatch):
    """An r5 city with unset sources.facilities uses Overpass — the engine
    choice must not silently switch the facility extraction."""
    calls: list = []
    _install_stubs(monkeypatch, tmp_path, calls)

    def boom(*a, **k):  # pbf extraction must not be reached
        raise AssertionError("extract_facilities (pbf) called")

    monkeypatch.setattr(osm, "extract_facilities", boom)
    cfg = _min_cfg(tmp_path, engine="r5")
    run_ingest(cfg, "testcity", tmp_path)
    assert (tmp_path / "data" / "derived" / "testcity"
            / "facilities_gp.parquet").exists()


def test_stale_network_marker_is_not_trusted(tmp_path):
    """The marker rides in the derived cache; the merged .pbf it points to may
    not exist on a fresh runner (run 30648450890 crashed with
    FileNotFoundError in its first minute). Missing marker, unreadable marker
    and stale target all mean "regenerate"; only marker+target means valid."""
    from depacc.ingest.pipeline import network_marker_valid

    marker = tmp_path / "network_pbf_path.txt"
    assert not network_marker_valid(marker)          # no marker at all

    marker.write_text(str(tmp_path / "gone.osm.pbf"))
    assert not network_marker_valid(marker)          # marker -> missing file

    pbf = tmp_path / "city_merged.osm.pbf"
    pbf.write_bytes(b"pbf")
    marker.write_text(str(pbf))
    assert network_marker_valid(marker)              # marker -> real file
