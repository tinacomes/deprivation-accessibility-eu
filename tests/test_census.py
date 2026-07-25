"""EU-harmonised census 2021 1 km ingest (Workstream D.1).

Exercises the whole path on synthetic in-memory files — INSPIRE grid-id
parsing in both published spellings, the chunked/bbox-clipped CSV reader
(plain and zipped), the share derivations with their per-share denominators
and "where published" skipping, and the 1 km -> 100 m broadcast join. No live
download is involved.
"""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from depacc.ingest.census import (
    census_layer,
    load_census_grid,
    parse_grid_id,
    share_columns,
)
from depacc.ingest.ses import join_ses_to_cells, ses_join_resolutions

# One 1 km cell: lower-left corner (E 4341000, N 2696000) -> centre +500 m.
FULL_ID = "CRS3035RES1000mN2696000E4341000"
SHORT_ID = "1kmN2696E4341"


def test_parse_grid_id_metre_and_km_spellings_agree():
    got = parse_grid_id(pd.Series([FULL_ID, SHORT_ID]))
    # INSPIRE ids name the LOWER-LEFT corner; we return cell centres.
    assert list(got.x) == [4341500.0, 4341500.0]
    assert list(got.y) == [2696500.0, 2696500.0]
    assert list(got.resolution_m) == [1000.0, 1000.0]


def test_parse_grid_id_handles_100m_ids_and_bad_rows():
    got = parse_grid_id(pd.Series(["CRS3035RES100mN2000E4000", "not-a-grid-id"]))
    assert (got.loc[0, "x"], got.loc[0, "y"]) == (4050.0, 2050.0)
    assert got.loc[0, "resolution_m"] == 100.0
    # A malformed row is NaN, not an exception — one bad line must not void a
    # continental file.
    assert np.isnan(got.loc[1, "x"])


def test_parse_grid_id_raises_when_nothing_parses():
    with pytest.raises(ValueError, match="No INSPIRE grid id"):
        parse_grid_id(pd.Series(["12345", "abcdef"]))


def _census_csv(sep: str = ",") -> str:
    header = sep.join(["GRD_ID", "T", "Y_LT15", "Y_15-64", "Y_GE65", "EMP"])
    rows = [
        sep.join([FULL_ID, "1000", "150", "600", "250", "420"]),
        # A neighbouring 1 km cell 1 km east.
        sep.join(["CRS3035RES1000mN2696000E4342000", "500", "50", "300", "150", "180"]),
        # Far away — must be clipped out by the bbox.
        sep.join(["CRS3035RES1000mN5000000E9000000", "10", "1", "8", "1", "4"]),
        # Eurostat confidentiality marker -> NaN, not a string.
        sep.join(["CRS3035RES1000mN2696000E4343000", ":", ":", ":", ":", ":"]),
    ]
    return "\n".join([header, *rows]) + "\n"


def test_load_census_grid_plain_csv_clips_to_bbox(tmp_path):
    path = tmp_path / "census.csv"
    path.write_text(_census_csv(), encoding="utf-8")
    bbox = (4341000.0, 2696000.0, 4343000.0, 2697000.0)
    # pad_m keeps cells whose centre falls just outside the FUA bbox — a 1 km
    # cell straddling the boundary still covers analysis cells inside it.
    grid = load_census_grid(path, bbox=bbox, columns=["T", "Y_GE65"],
                            chunksize=2, pad_m=1000.0)
    assert list(grid.columns) == ["x", "y", "T", "Y_GE65"]
    assert sorted(grid.x) == [4341500.0, 4342500.0, 4343500.0]
    # NB: always subscript the total-population column — `grid.T` is the
    # DataFrame transpose, and the census code for total population IS "T".
    assert grid["T"].notna().sum() == 2  # the ':' row coerced to NaN
    assert grid.loc[grid.x == 4341500.0, "Y_GE65"].iloc[0] == 250.0

    # Without the pad the straddling cell is dropped, and the far-away cell is
    # never in either result.
    tight = load_census_grid(path, bbox=bbox, columns=["T"], pad_m=0.0)
    assert sorted(tight.x) == [4341500.0, 4342500.0]


def test_load_census_grid_reads_semicolon_csv_inside_zip(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        # A small metadata CSV alongside the data table: the largest .csv wins.
        zf.writestr("metadata.csv", "code;label\nT;Total population\n")
        zf.writestr("grid_1km.csv", _census_csv(sep=";"))
    grid = load_census_grid(path, columns=["T", "EMP"])
    assert list(grid.columns) == ["x", "y", "T", "EMP"]
    assert len(grid) == 4  # no bbox -> everything, including the far cell
    assert grid.loc[grid.x == 4341500.0, "EMP"].iloc[0] == 420.0


def test_load_census_grid_member_selects_the_named_csv(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("grid_1km.csv", _census_csv())
        # A DECOY that is larger, so "largest .csv" would pick the wrong one.
        zf.writestr("grid_10km.csv", _census_csv() + _census_csv().split("\n", 1)[1] * 5)
    grid = load_census_grid(path, member="grid_1km", columns=["T"])
    assert len(grid) == 4


def test_data_member_skips_raster_and_documentation(tmp_path):
    """The real v1.0 archive: the tabular data is a GeoPackage, and the other
    members (raster, PDF, read.me, a nested INSPIRE country zip) must never be
    mistaken for it."""
    from depacc.ingest.census import _data_member

    path = tmp_path / "Eurostat_Census-GRID_2021_V1-0.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("CENSUS_INS21ES_A_IT_2021_0000_TOTAL _POPULATION.zip", "x" * 900)
        zf.writestr("ESMS_Census_Grid 2021.pdf", "x" * 500)
        zf.writestr("ESTAT_Census_2021_V1-0.gpkg", "x" * 100)
        zf.writestr("ESTAT_OBS-VALUE-T_2021_V1-0.tiff", "x" * 800)
        zf.writestr("read.me", "x")
    with zipfile.ZipFile(path) as zf:
        # Picked on extension preference, not on being the largest member.
        assert _data_member(zf, None) == "ESTAT_Census_2021_V1-0.gpkg"
        assert _data_member(zf, "OBS-VALUE") == "ESTAT_OBS-VALUE-T_2021_V1-0.tiff"


def test_data_member_prefers_gpkg_over_a_metadata_csv(tmp_path):
    from depacc.ingest.census import _data_member

    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("codes.csv", "x" * 5000)
        zf.writestr("ESTAT_Census_2021_V1-0.gpkg", "x" * 10)
    with zipfile.ZipFile(path) as zf:
        assert _data_member(zf, None).endswith(".gpkg")


def test_extract_member_is_cached(tmp_path):
    from depacc.ingest.census import _extract_member

    path = tmp_path / "census.zip"
    payload = b"gpkg-bytes" * 100
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ESTAT_Census_2021_V1-0.gpkg", payload)
    with zipfile.ZipFile(path) as zf:
        first = _extract_member(zf, "ESTAT_Census_2021_V1-0.gpkg", tmp_path / "unpacked")
        assert first.read_bytes() == payload
        mtime = first.stat().st_mtime_ns
        again = _extract_member(zf, "ESTAT_Census_2021_V1-0.gpkg", tmp_path / "unpacked")
    # Second call reuses the extracted copy (same size) rather than rewriting it.
    assert again == first and again.stat().st_mtime_ns == mtime


def test_load_census_grid_warns_on_absent_column(tmp_path, capsys):
    path = tmp_path / "census.csv"
    path.write_text(_census_csv(), encoding="utf-8")
    grid = load_census_grid(path, columns=["T", "EU_OTH"])
    # The unpublished (voluntary) variable is reported and simply not present.
    assert "EU_OTH" in capsys.readouterr().out
    assert list(grid.columns) == ["x", "y", "T"]


def test_load_census_grid_matches_columns_case_insensitively(tmp_path):
    path = tmp_path / "census.csv"
    path.write_text("grd_id,t,y_ge65\n" + f"{FULL_ID},1000,250\n", encoding="utf-8")
    grid = load_census_grid(path, columns=["T", "Y_GE65"])
    # Config codes, not the file's casing, name the columns downstream.
    assert list(grid.columns) == ["x", "y", "T", "Y_GE65"]
    assert grid.loc[0, "Y_GE65"] == 250.0


SHARE_SPEC = {
    "share_u15": {"numerator": ["Y_LT15"], "denominator": ["T"]},
    "share_ge65": {"numerator": ["Y_GE65"], "denominator": ["T"]},
    "employment_share": {"numerator": ["EMP"], "denominator": ["Y_15-64"]},
    "foreign_born_share": {"numerator": ["EU_OTH", "OTH"], "denominator": ["T"]},
}


def test_share_columns_uses_per_share_denominator_and_skips_unpublished():
    df = pd.DataFrame({"T": [1000.0, 0.0], "Y_LT15": [150.0, 0.0],
                       "Y_15-64": [600.0, 0.0], "Y_GE65": [250.0, 0.0],
                       "EMP": [420.0, 0.0]})
    out = share_columns(df, SHARE_SPEC)
    assert out.loc[0, "share_u15"] == 0.15
    assert out.loc[0, "share_ge65"] == 0.25
    # Employment is over the WORKING-AGE base, not the total population.
    assert out.loc[0, "employment_share"] == pytest.approx(420.0 / 600.0)
    # Country-of-birth columns absent -> the share is skipped, never zero-filled.
    assert "foreign_born_share" not in out.columns
    # Zero denominator -> NaN, never a division blow-up.
    assert np.isnan(out.loc[1, "share_u15"])


def test_share_columns_sums_multi_category_numerator():
    df = pd.DataFrame({"T": [1000.0], "EU_OTH": [80.0], "OTH": [np.nan]})
    out = share_columns(df, {"foreign_born_share": SHARE_SPEC["foreign_born_share"]})
    # A suppressed category counts as zero rather than voiding the whole share.
    assert out.loc[0, "foreign_born_share"] == 0.08


def test_join_broadcasts_1km_census_onto_100m_cells():
    # Four 100 m analysis cells inside ONE 1 km census cell, plus one outside.
    inside = [(4341050.0, 2696050.0), (4341950.0, 2696950.0),
              (4341550.0, 2696450.0), (4341150.0, 2696850.0)]
    outside = (4342050.0, 2696050.0)  # the next kilometre east
    cells = pd.DataFrame({
        "cell_id": [f"c{i}" for i in range(5)],
        "x": [x for x, _ in inside] + [outside[0]],
        "y": [y for _, y in inside] + [outside[1]],
        "population": [10.0] * 5,
    })
    census = pd.DataFrame({"x": [4341500.0], "y": [2696500.0],
                           "share_ge65": [0.25], "share_u15": [0.15]})
    out = join_ses_to_cells(cells, {"census": census}, resolutions={"census": 1000})

    # Every 100 m cell in the kilometre inherits the same value (broadcast).
    assert list(out.loc[:3, "ses_census_share_ge65"]) == [0.25] * 4
    assert list(out.loc[:3, "ses_census_share_u15"]) == [0.15] * 4
    # The cell in the uncovered neighbouring kilometre stays NaN — never the
    # nearest neighbour's value.
    assert np.isnan(out.loc[4, "ses_census_share_ge65"])


def test_join_keeps_layers_on_their_own_resolutions():
    # One 1 km census layer and one native 100 m layer joined in a single pass:
    # the 100 m layer must NOT be smeared over the kilometre.
    cells = pd.DataFrame({
        "cell_id": ["a", "b"],
        "x": [4341050.0, 4341950.0],
        "y": [2696050.0, 2696050.0],
    })
    census = pd.DataFrame({"x": [4341500.0], "y": [2696500.0], "share_ge65": [0.25]})
    rent = pd.DataFrame({"x": [4341050.0], "y": [2696050.0], "qm": [8.0]})
    out = join_ses_to_cells(cells, {"census": census, "net_rent": rent},
                            resolutions={"census": 1000, "net_rent": 100})
    assert list(out["ses_census_share_ge65"]) == [0.25, 0.25]      # broadcast
    assert out.loc[0, "ses_net_rent_qm"] == 8.0            # native 100 m
    assert np.isnan(out.loc[1, "ses_net_rent_qm"])         # not broadcast


def test_join_reads_resolution_from_layer_attrs():
    cells = pd.DataFrame({"cell_id": ["a"], "x": [4341050.0], "y": [2696050.0]})
    census = pd.DataFrame({"x": [4341500.0], "y": [2696500.0], "share_ge65": [0.25]})
    census.attrs["resolution_m"] = 1000
    out = join_ses_to_cells(cells, {"census": census})  # default is 100 m
    assert out.loc[0, "ses_census_share_ge65"] == 0.25


def test_ses_join_resolutions_flags_broadcast_layers():
    census = pd.DataFrame({"x": [0.0], "y": [0.0], "share_ge65": [0.2],
                           "share_u15": [0.1]})
    rent = pd.DataFrame({"x": [0.0], "y": [0.0], "qm": [8.0]})
    prov = ses_join_resolutions({"census": census, "net_rent": rent},
                                resolutions={"census": 1000, "net_rent": 100})
    assert prov["census"]["broadcast_to_analysis_grid"] is True
    assert prov["census"]["columns"] == ["ses_census_share_ge65",
                                         "ses_census_share_u15"]
    assert prov["net_rent"]["broadcast_to_analysis_grid"] is False
    assert prov["net_rent"]["columns"] == ["ses_net_rent_qm"]


def _census_cfg(tmp_path, url: str) -> dict:
    return {
        "output": {"raw_root": "raw", "cache_root": "cache"},
        "sources": {"census": {
            "url": url, "resolution_m": 1000, "id_column": "GRD_ID",
            "shares": SHARE_SPEC, "licence": "CC-BY 4.0",
        }},
    }


class _Bounds:
    """Minimal stand-in for the FUA GeoDataFrame (only total_bounds is used)."""

    total_bounds = np.array([4341000.0, 2696000.0, 4343000.0, 2697000.0])


def test_census_layer_end_to_end_from_a_local_file(tmp_path, monkeypatch):
    src = tmp_path / "census.csv"
    src.write_text(_census_csv(), encoding="utf-8")
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: {"grid": src})
    layer = census_layer(_census_cfg(tmp_path, "file://x"), tmp_path, _Bounds())
    # Only the derived shares survive (counts are dropped; population comes
    # from GHS-POP), and the far-away cell is clipped out.
    assert list(layer.columns) == ["x", "y", "share_u15", "share_ge65",
                                   "employment_share"]
    assert layer.loc[layer.x == 4341500.0, "share_ge65"].iloc[0] == 0.25


def test_census_layer_returns_none_without_a_url(tmp_path, capsys):
    cfg = {"output": {"raw_root": "raw"}, "sources": {"census": {}}}
    assert census_layer(cfg, tmp_path, _Bounds()) is None
    assert "sources.census.url" in capsys.readouterr().out


def test_census_layer_survives_a_failed_download(tmp_path, monkeypatch, capsys):
    import requests

    def _boom(url, dest, **kwargs):
        # What a moved GISCO release actually raises through provenance.download.
        raise requests.HTTPError("404 Not Found")

    monkeypatch.setattr("depacc.ingest.census.download", _boom)
    cfg = _census_cfg(tmp_path, "https://example.invalid/census.zip")
    # A moved GISCO release degrades one city's covariates; it must not kill an
    # all-city batch run.
    assert census_layer(cfg, tmp_path, _Bounds()) is None
    assert "continuing without" in capsys.readouterr().out


def test_census_layer_returns_none_when_no_cell_overlaps(tmp_path, monkeypatch):
    src = tmp_path / "census.csv"
    src.write_text(_census_csv(), encoding="utf-8")
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: {"grid": src})

    class _Elsewhere:
        total_bounds = np.array([0.0, 0.0, 1000.0, 1000.0])

    assert census_layer(_census_cfg(tmp_path, "file://x"), tmp_path,
                        _Elsewhere()) is None


def test_load_census_grid_rejects_an_archive_with_no_readable_table(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ESTAT_OBS-VALUE-T_2021_V1-0.tiff", "raster only")
        zf.writestr("read.me", "docs")
    with pytest.raises(ValueError, match="No readable census table"):
        load_census_grid(path)


def test_load_census_grid_rejects_a_missing_id_column(tmp_path):
    path = tmp_path / "census.csv"
    path.write_text("cell,T\nfoo,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="census id column"):
        load_census_grid(path)


def test_member_error_lists_the_archive_contents(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("grid_1km.csv", _census_csv())
    with pytest.raises(ValueError, match="matches nothing"):
        load_census_grid(path, member="nope")


def test_bytesio_fixture_helper_is_unused_but_zip_roundtrips(tmp_path):
    # Guards the reader against a zip written from a stream (as the fixtures in
    # tests/test_ses.py do) rather than from a file path.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("grid.csv", _census_csv())
    path = tmp_path / "stream.zip"
    path.write_bytes(buf.getvalue())
    assert len(load_census_grid(path, columns=["T"])) == 4


# ---------------------------------------------------------------------------
# The GeoPackage path — the form the v1.0 GISCO release actually ships. Needs
# geopandas, which is an optional extra, so it skips on the light CI install.
# ---------------------------------------------------------------------------

def _write_census_gpkg(path, *, with_grd_id: bool = True):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    rows = [
        (FULL_ID, 4341000, 2696000, 1000, 150, 600, 250, 420),
        ("CRS3035RES1000mN2696000E4342000", 4342000, 2696000, 500, 50, 300, 150, 180),
        ("CRS3035RES1000mN5000000E9000000", 9000000, 5000000, 10, 1, 8, 1, 4),
    ]
    frame = gpd.GeoDataFrame(
        {
            "GRD_ID": [r[0] for r in rows],
            "T": [r[3] for r in rows],
            "Y_LT15": [r[4] for r in rows],
            "Y_15-64": [r[5] for r in rows],
            "Y_GE65": [r[6] for r in rows],
            "EMP": [r[7] for r in rows],
        },
        geometry=[box(r[1], r[2], r[1] + 1000, r[2] + 1000) for r in rows],
        crs="EPSG:3035",
    )
    if not with_grd_id:
        frame = frame.drop(columns=["GRD_ID"])
    frame.to_file(path, driver="GPKG")
    return path


def test_load_census_grid_reads_a_geopackage_clipped_to_the_fua(tmp_path):
    pytest.importorskip("geopandas")
    gpkg = _write_census_gpkg(tmp_path / "ESTAT_Census_2021_V1-0.gpkg")
    bbox = (4341000.0, 2696000.0, 4343000.0, 2697000.0)
    grid = load_census_grid(gpkg, bbox=bbox, columns=["T", "Y_GE65"])
    assert list(grid.columns) == ["x", "y", "T", "Y_GE65"]
    # Cell centres from GRD_ID, and the far-away cell clipped out.
    assert sorted(grid.x) == [4341500.0, 4342500.0]
    assert grid.loc[grid.x == 4341500.0, "Y_GE65"].iloc[0] == 250.0
    assert "geometry" not in grid.columns


def test_load_census_grid_falls_back_to_geometry_without_grd_id(tmp_path):
    pytest.importorskip("geopandas")
    gpkg = _write_census_gpkg(tmp_path / "nogrd.gpkg", with_grd_id=False)
    grid = load_census_grid(gpkg, columns=["T"])
    # Polygon representative points recover the same cell centres.
    assert sorted(grid.x)[:2] == [4341500.0, 4342500.0]


def test_load_census_grid_reads_the_gpkg_out_of_the_published_zip(tmp_path):
    """End to end on an archive shaped like the real one: gpkg + raster + docs."""
    pytest.importorskip("geopandas")
    gpkg = _write_census_gpkg(tmp_path / "ESTAT_Census_2021_V1-0.gpkg")
    archive = tmp_path / "Eurostat_Census-GRID_2021_V1-0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(gpkg, "ESTAT_Census_2021_V1-0.gpkg")
        zf.writestr("ESTAT_OBS-VALUE-T_2021_V1-0.tiff", "x" * 10_000)
        zf.writestr("ESMS_Census_Grid 2021.pdf", "x" * 5_000)
        zf.writestr("read.me", "docs")
    gpkg.unlink()  # only the archive remains, as after a fresh download

    grid = load_census_grid(archive, bbox=(4341000.0, 2696000.0, 4343000.0, 2697000.0),
                            columns=["T", "Y_GE65", "Y_15-64", "EMP"])
    assert sorted(grid.x) == [4341500.0, 4342500.0]
    # The gpkg was unpacked once beside the archive, for the batch's re-reads.
    assert (tmp_path / "unpacked" / "ESTAT_Census_2021_V1-0.gpkg").exists()

    shares = share_columns(grid, SHARE_SPEC)
    assert shares.loc[shares.x == 4341500.0, "share_ge65"].iloc[0] == 0.25
    assert shares.loc[shares.x == 4341500.0, "employment_share"].iloc[0] == pytest.approx(0.7)


def test_census_layer_unpacks_under_the_cache_root_not_data_raw(tmp_path):
    """The workflows cache data/raw wholesale per city, so a continental
    GeoPackage unpacked there would be stored once per city and could evict the
    OSM extracts. It belongs under the cache root."""
    pytest.importorskip("geopandas")
    gpkg = _write_census_gpkg(tmp_path / "ESTAT_Census_2021_V1-0.gpkg")
    url = "https://example.invalid/Eurostat_Census-GRID_2021_V1-0.zip"
    archive = tmp_path / "raw" / "census" / url.rsplit("/", 1)[-1]
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(gpkg, "ESTAT_Census_2021_V1-0.gpkg")
    gpkg.unlink()
    # A cached archive is one with its provenance sidecar; no network needed.
    archive.with_name(archive.name + ".provenance.json").write_text("{}")

    cfg = _census_cfg(tmp_path, url)
    layer = census_layer(cfg, tmp_path, _Bounds())  # archive already cached
    assert layer is not None and not layer.empty
    assert (tmp_path / "cache" / "census" / "ESTAT_Census_2021_V1-0.gpkg").exists()
    assert not (tmp_path / "raw" / "census" / "unpacked").exists()


# ---------------------------------------------------------------------------
# What the first real run actually found: the v1.0 GeoPackage's default layer
# carries only ['GRD_ID', 'OBS_VALUE_T']. Two things follow — the codes are
# wrapped as OBS_VALUE_<CODE>, and the other variables are not in that layer.
# ---------------------------------------------------------------------------

def test_code_matches_unwraps_obs_value_without_matching_partial_words():
    from depacc.ingest.census import code_matches

    assert code_matches("OBS_VALUE_T", "T")
    assert code_matches("obs_value_y_ge65", "Y_GE65")
    assert code_matches("ESTAT_OBS-VALUE-Y_LT15_2021_V1-0", "Y_LT15")
    assert code_matches("T", "T")
    # "T" must not be found inside another code, or every share collapses onto
    # total population.
    assert not code_matches("OBS_VALUE_Y_LT15", "T")
    assert not code_matches("OBS_VALUE_EMP", "T")
    assert not code_matches("OBS_VALUE_Y_GE65", "Y_LT15")


def test_resolve_columns_unwraps_obs_value_codes(tmp_path):
    path = tmp_path / "census.csv"
    path.write_text(f"GRD_ID,OBS_VALUE_T,OBS_VALUE_Y_GE65\n{FULL_ID},1000,250\n",
                    encoding="utf-8")
    grid = load_census_grid(path, columns=["T", "Y_GE65"])
    # Config codes name the columns even though the file wraps them.
    assert list(grid.columns) == ["x", "y", "T", "Y_GE65"]
    assert grid.loc[0, "T"] == 1000.0 and grid.loc[0, "Y_GE65"] == 250.0


def test_resolve_columns_skips_an_ambiguous_code(tmp_path, capsys):
    path = tmp_path / "census.csv"
    path.write_text(f"GRD_ID,OBS_VALUE_T,COUNT_T\n{FULL_ID},1000,999\n",
                    encoding="utf-8")
    grid = load_census_grid(path, columns=["T"])
    out = capsys.readouterr().out
    assert "matches" in out and "skipping it" in out
    assert "T" not in grid.columns  # never silently pick one of two


def _write_per_variable_gpkg(path):
    """A GeoPackage with ONE LAYER PER VARIABLE, as the census release appears
    to be organised: each layer holds the grid id plus its own OBS_VALUE_*."""
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    cells = [(4341000, 2696000), (4342000, 2696000)]
    for code, values in (("T", [1000, 500]), ("Y_LT15", [150, 50]),
                         ("Y_GE65", [250, 150]), ("Y_15-64", [600, 300]),
                         ("EMP", [420, 180])):
        gpd.GeoDataFrame(
            {"GRD_ID": [f"CRS3035RES1000mN{y}E{x}" for x, y in cells],
             f"OBS_VALUE_{code}": values},
            geometry=[box(x, y, x + 1000, y + 1000) for x, y in cells],
            crs="EPSG:3035",
        ).to_file(path, driver="GPKG", layer=f"ESTAT_OBS-VALUE-{code}_2021_V1-0")
    return path


def test_load_census_grid_merges_per_variable_gpkg_layers(tmp_path):
    pytest.importorskip("geopandas")
    gpkg = _write_per_variable_gpkg(tmp_path / "ESTAT_Census_2021_V1-0.gpkg")
    grid = load_census_grid(gpkg, columns=["T", "Y_LT15", "Y_GE65", "Y_15-64", "EMP"])
    # Every requested variable found its own layer and merged on the centroid.
    assert set(grid.columns) == {"x", "y", "T", "Y_LT15", "Y_GE65", "Y_15-64", "EMP"}
    assert len(grid) == 2
    row = grid[grid.x == 4341500.0].iloc[0]
    assert (row["T"], row["Y_GE65"], row["EMP"]) == (1000.0, 250.0, 420.0)

    shares = share_columns(grid, SHARE_SPEC)
    top = shares[shares.x == 4341500.0].iloc[0]
    assert top.share_ge65 == 0.25 and top.share_u15 == 0.15
    assert top.employment_share == pytest.approx(0.7)


def test_load_census_grid_reports_layers_and_falls_back_to_the_default(
        tmp_path, capsys):
    """A code that names no layer must not be mistaken for a missing file: the
    inventory is printed and the default layer read, so the run reports what the
    release really contains."""
    pytest.importorskip("geopandas")
    gpkg = _write_per_variable_gpkg(tmp_path / "ESTAT_Census_2021_V1-0.gpkg")
    grid = load_census_grid(gpkg, columns=["NOT_A_CODE"])
    out = capsys.readouterr().out
    assert "layer(s) in ESTAT_Census_2021_V1-0.gpkg" in out
    assert "names a layer" in out
    assert list(grid.columns) == ["x", "y"]  # nothing usable, reported not raised


def test_census_layer_reports_the_variables_it_did_load(tmp_path, monkeypatch,
                                                        capsys):
    """The failure the first run hit: the file loads fine but publishes none of
    the configured variables. The message must name what it DID find."""
    src = tmp_path / "census.csv"
    src.write_text(f"GRD_ID,OBS_VALUE_T\n{FULL_ID},1000\n", encoding="utf-8")
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: {"grid": src})
    assert census_layer(_census_cfg(tmp_path, "file://x"), tmp_path, _Bounds()) is None
    out = capsys.readouterr().out
    assert "no census shares could be derived" in out
    assert "the loaded variables were ['T']" in out


def test_fetch_census_grid_supports_per_variable_urls(tmp_path, monkeypatch):
    """`sources.census.urls` mirrors sources.ses.urls, for a release that ships
    one file per variable."""
    from depacc.ingest.census import fetch_census_grid

    calls = []

    def _fake_download(url, dest, **kwargs):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("x")
        return dest

    monkeypatch.setattr("depacc.ingest.census.download", _fake_download)
    cfg = {"output": {"raw_root": "raw"}, "sources": {"census": {
        "urls": {"T": "https://x.invalid/T.csv",
                 "Y_GE65": "https://x.invalid/Y_GE65.csv"}}}}
    paths = fetch_census_grid(cfg, tmp_path)
    assert sorted(paths) == ["T", "Y_GE65"]
    assert paths["T"].name == "T.csv"
    assert len(calls) == 2


def test_census_layer_merges_per_variable_files(tmp_path, monkeypatch):
    files = {}
    for code, value in (("T", 1000), ("Y_GE65", 250)):
        p = tmp_path / f"{code}.csv"
        p.write_text(f"GRD_ID,OBS_VALUE_{code}\n{FULL_ID},{value}\n", encoding="utf-8")
        files[code] = p
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: files)
    layer = census_layer(_census_cfg(tmp_path, "file://x"), tmp_path, _Bounds())
    # Only share_ge65 is derivable from T + Y_GE65; the rest skip cleanly.
    assert list(layer.columns) == ["x", "y", "share_ge65"]
    assert layer.loc[0, "share_ge65"] == 0.25


# ---------------------------------------------------------------------------
# Shared-source prefetch: the national/continental archives are one file for
# many cities, so a batch fetches them once instead of once per runner.
# ---------------------------------------------------------------------------

def test_prefetch_fetches_one_census_and_one_ses_set_per_country(tmp_path, monkeypatch):
    from depacc.ingest import prefetch as pf

    census_calls, ses_calls, tile_calls = [], [], []
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: census_calls.append(
                            cfg["sources"]["census"]["url"]) or {})
    monkeypatch.setattr("depacc.ingest.ses.fetch_ses_layers",
                        lambda cfg, root: ses_calls.append(
                            sorted(cfg["sources"]["ses"]["urls"])) or {})
    monkeypatch.setattr("depacc.ingest.boundaries.fetch_fua_boundary",
                        lambda cfg, root: None)

    # Two German cities sharing one census URL and one Zensus URL set.
    done = pf.prefetch_shared(["hamburg", "hamburg"], tmp_path)
    assert len(census_calls) == 1, "the EU census grid must be fetched once"
    assert len(ses_calls) == 1, "one Zensus set serves every German city"
    assert not tile_calls
    assert set(done) == {"boundaries", "census", "ses", "ghs"}


def test_prefetch_survives_an_unreachable_source(tmp_path, monkeypatch):
    """A prep job that cannot reach one source must not block the batch — the
    per-city runs then fetch what they can and warn for themselves."""
    from depacc.ingest import prefetch as pf

    def _boom(cfg, root):
        raise OSError("network down")

    monkeypatch.setattr("depacc.ingest.boundaries.fetch_fua_boundary", _boom)
    monkeypatch.setattr("depacc.ingest.census.fetch_census_grid",
                        lambda cfg, root: {})
    monkeypatch.setattr("depacc.ingest.ses.fetch_ses_layers", _boom)
    assert pf.prefetch_shared(["hamburg"], tmp_path)["boundaries"] == []


def test_shared_and_city_raw_dirs_are_disjoint_and_cover_the_pipeline():
    """The two CI caches must not overlap, or they fight over the same files."""
    from depacc.ingest.prefetch import CITY_RAW_DIRS, SHARED_RAW_DIRS

    assert not set(SHARED_RAW_DIRS) & set(CITY_RAW_DIRS)
    # Every data/raw/<dir> the pipeline writes must be in exactly one cache.
    import re
    from pathlib import Path

    used = set()
    for src in Path("src/depacc").rglob("*.py"):
        used |= set(re.findall(r'raw_root"\]\s*/\s*"([a-z_]+)"', src.read_text()))
    assert used <= set(SHARED_RAW_DIRS) | set(CITY_RAW_DIRS), (
        f"raw sub-dirs missing from the cache split: "
        f"{sorted(used - set(SHARED_RAW_DIRS) - set(CITY_RAW_DIRS))}")


def test_workflow_cache_paths_match_the_declared_split():
    """The workflows' SHARED/CITY cache paths are the same split the code
    declares — they drift silently otherwise."""
    import re
    from pathlib import Path

    from depacc.ingest.prefetch import CITY_RAW_DIRS, SHARED_RAW_DIRS

    for wf in ("run-city.yml", "tier1-batch.yml"):
        text = Path(".github/workflows") / wf
        content = text.read_text()
        for var, dirs in (("SHARED_RAW_PATHS", SHARED_RAW_DIRS),
                          ("CITY_RAW_PATHS", CITY_RAW_DIRS)):
            block = re.search(rf"{var}: \|\n((?:\s+data/raw/\w+\n)+)", content)
            assert block, f"{var} missing from {wf}"
            listed = set(re.findall(r"data/raw/(\w+)", block.group(1)))
            assert listed == set(dirs), f"{wf}:{var} lists {sorted(listed)}"
