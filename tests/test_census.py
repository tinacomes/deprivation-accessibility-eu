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
    assert list(out["ses_census"]) == [0.25, 0.25]      # broadcast
    assert out.loc[0, "ses_net_rent"] == 8.0            # native 100 m
    assert np.isnan(out.loc[1, "ses_net_rent"])         # not broadcast


def test_join_reads_resolution_from_layer_attrs():
    cells = pd.DataFrame({"cell_id": ["a"], "x": [4341050.0], "y": [2696050.0]})
    census = pd.DataFrame({"x": [4341500.0], "y": [2696500.0], "share_ge65": [0.25]})
    census.attrs["resolution_m"] = 1000
    out = join_ses_to_cells(cells, {"census": census})  # default is 100 m
    assert out.loc[0, "ses_census"] == 0.25


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
    assert prov["net_rent"]["columns"] == ["ses_net_rent"]


def _census_cfg(tmp_path, url: str) -> dict:
    return {
        "output": {"raw_root": "raw"},
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
                        lambda cfg, root: src)
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
                        lambda cfg, root: src)

    class _Elsewhere:
        total_bounds = np.array([0.0, 0.0, 1000.0, 1000.0])

    assert census_layer(_census_cfg(tmp_path, "file://x"), tmp_path,
                        _Elsewhere()) is None


def test_load_census_grid_rejects_an_archive_without_csv(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("grid.gpkg", "not a csv")
    with pytest.raises(ValueError, match="No .csv member"):
        load_census_grid(path)


def test_load_census_grid_rejects_a_missing_id_column(tmp_path):
    path = tmp_path / "census.csv"
    path.write_text("cell,T\nfoo,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="census id column"):
        load_census_grid(path)


def test_csv_member_error_lists_the_archive_contents(tmp_path):
    path = tmp_path / "census.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("grid_1km.csv", _census_csv())
    with pytest.raises(ValueError, match="matches no .csv"):
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
