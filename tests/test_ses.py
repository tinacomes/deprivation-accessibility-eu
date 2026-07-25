"""Tier-2 SES ingest: INSPIRE 100 m grid loading, cell join and age shares.

Exercises the Zensus-2022-style loader path on a synthetic in-memory grid
(semicolon-separated, German decimal commas, '–'/empty for suppressed cells)
so the join semantics and NaN handling are pinned without any live download.
"""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from depacc.ingest.pipeline import _derive_ses_columns
from depacc.ingest.ses import (
    age_group_shares,
    join_ses_to_cells,
    load_inspire_csv_zip,
)


def _age_cfg():
    return {"sources": {"ses": {"derived": {"age_shares": {
        "population_col": "ses_age_structure_Insgesamt_Bevoelkerung",
        "bands": {
            "ses_age_share_u18": ["ses_age_structure_Unter18"],
            "ses_age_share_ge65": ["ses_age_structure_a65undaelter"],
        }}}}}}


def test_derive_ses_columns_adds_age_shares():
    cells = pd.DataFrame({
        "cell_id": ["a", "b"],
        "ses_age_structure_Insgesamt_Bevoelkerung": [100.0, 200.0],
        "ses_age_structure_Unter18": [18.0, 40.0],
        "ses_age_structure_a65undaelter": [25.0, 60.0],
    })
    out = _derive_ses_columns(_age_cfg(), cells)
    assert out.loc[0, "ses_age_share_u18"] == 0.18
    assert out.loc[1, "ses_age_share_ge65"] == 0.30


def test_derive_ses_columns_skips_when_columns_absent():
    # A layer failed to join -> the source columns are missing; derivation is
    # skipped (warned) rather than raising, so ingest still completes.
    cells = pd.DataFrame({"cell_id": ["a"], "population": [10.0]})
    out = _derive_ses_columns(_age_cfg(), cells)
    assert "ses_age_share_u18" not in out.columns
    assert list(out.columns) == ["cell_id", "population"]


def test_derive_ses_columns_noop_without_config():
    cells = pd.DataFrame({"cell_id": ["a"], "population": [10.0]})
    assert _derive_ses_columns({}, cells).equals(cells)


def _make_inspire_zip(rows: str, header: str, name: str = "grid_100m.csv") -> io.BytesIO:
    """Zip a single Zensus-style INSPIRE CSV (';'-sep, decimal ',') in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, header + "\n" + rows)
    buf.seek(0)
    return buf


def test_load_inspire_csv_zip_parses_german_format(tmp_path):
    header = "GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner;Durchschnittsalter"
    rows = "\n".join([
        "CRS3035RES100mN2000E4000;4050;2050;123;42,5",
        "CRS3035RES100mN2000E4100;4150;2050;–;",  # suppressed cell -> NaN
    ])
    zpath = tmp_path / "pop.zip"
    zpath.write_bytes(_make_inspire_zip(rows, header).getvalue())

    df = load_inspire_csv_zip(zpath)
    # x/y renamed from the x_mp*/y_mp* centroid columns; GITTER id dropped.
    assert list(df.columns) == ["x", "y", "Einwohner", "Durchschnittsalter"]
    assert df.loc[0, "x"] == 4050 and df.loc[0, "y"] == 2050
    assert df.loc[0, "Einwohner"] == 123
    assert df.loc[0, "Durchschnittsalter"] == 42.5
    # Suppressed cell coerces to NaN, not a string.
    assert np.isnan(df.loc[1, "Einwohner"])
    assert np.isnan(df.loc[1, "Durchschnittsalter"])


def test_load_inspire_csv_zip_drops_annotation_column(tmp_path):
    # The `werterlaeuternde_Zeichen` annotation field must not survive as data.
    header = ("GITTER_ID_100m;x_mp_100m;y_mp_100m;"
              "Eigentuemerquote;werterlaeuternde_Zeichen")
    rows = "CRS3035RES100mN2000E4000;4050;2050;41,2;/"
    zpath = tmp_path / "own.zip"
    zpath.write_bytes(_make_inspire_zip(rows, header).getvalue())

    df = load_inspire_csv_zip(zpath)
    assert list(df.columns) == ["x", "y", "Eigentuemerquote"]
    assert df.loc[0, "Eigentuemerquote"] == 41.2


def test_load_inspire_csv_zip_respects_value_columns(tmp_path):
    header = "GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner;Nettokaltmiete"
    rows = "CRS3035RES100mN2000E4000;4050;2050;10;7,80"
    zpath = tmp_path / "rent.zip"
    zpath.write_bytes(_make_inspire_zip(rows, header).getvalue())

    df = load_inspire_csv_zip(zpath, value_columns=["Nettokaltmiete"])
    assert list(df.columns) == ["x", "y", "Nettokaltmiete"]
    assert df.loc[0, "Nettokaltmiete"] == 7.80


def test_join_ses_to_cells_snaps_to_100m_grid():
    # Two GHS cells; centroids fall inside the same 100 m INSPIRE cells as the
    # SES layer rows below (INSPIRE coords are cell CENTRES).
    cells = pd.DataFrame({
        "cell_id": ["a", "b", "c"],
        "x": [4050.0, 4150.0, 9999.0],  # 'c' has no matching SES cell
        "y": [2050.0, 2050.0, 2050.0],
        "population": [100.0, 50.0, 10.0],
    })
    rent = pd.DataFrame({"x": [4030.0, 4180.0], "y": [2010.0, 2099.0],
                         "Nettokaltmiete": [8.0, 9.5]})
    out = join_ses_to_cells(cells, {"net_rent": rent})

    # Single-value layer -> flat 'ses_<name>' column (no per-column suffix).
    assert "ses_net_rent" in out.columns
    assert out.loc[0, "ses_net_rent"] == 8.0
    assert out.loc[1, "ses_net_rent"] == 9.5
    # Cell with no SES cell in the layer -> NaN, never a wrong neighbour.
    assert np.isnan(out.loc[2, "ses_net_rent"])
    # Original columns are preserved.
    assert list(out["population"]) == [100.0, 50.0, 10.0]


def test_join_ses_to_cells_multicolumn_layer_suffixes_names():
    cells = pd.DataFrame({"cell_id": ["a"], "x": [4050.0], "y": [2050.0]})
    age = pd.DataFrame({"x": [4050.0], "y": [2050.0],
                        "share_u15": [0.12], "share_ge65": [0.28]})
    out = join_ses_to_cells(cells, {"age": age})
    assert out.loc[0, "ses_age_share_u15"] == 0.12
    assert out.loc[0, "ses_age_share_ge65"] == 0.28


def test_join_ses_to_cells_dedupes_layer_grid_collisions():
    # Two SES rows collide onto the same 100 m cell -> first kept, no crash.
    cells = pd.DataFrame({"cell_id": ["a"], "x": [4050.0], "y": [2050.0]})
    layer = pd.DataFrame({"x": [4010.0, 4090.0], "y": [2010.0, 2090.0],
                          "v": [1.0, 2.0]})
    out = join_ses_to_cells(cells, {"layer": layer})
    assert out.loc[0, "ses_layer"] == 1.0


def test_age_group_shares_over_explicit_population():
    df = pd.DataFrame({
        "pop": [100.0, 200.0, 0.0],
        "u3": [5, 10, 0], "3_14": [10, 30, 0],
        "65_74": [15, 20, 0], "ge75": [10, 20, 0],
    })
    out = age_group_shares(
        df,
        bands={"share_u15": ["u3", "3_14"], "share_ge65": ["65_74", "ge75"]},
        population_col="pop",
    )
    assert out.loc[0, "share_u15"] == (5 + 10) / 100
    assert out.loc[0, "share_ge65"] == (15 + 10) / 100
    assert out.loc[1, "share_u15"] == (10 + 30) / 200
    # Zero population -> NaN share, never a divide-by-zero.
    assert np.isnan(out.loc[2, "share_u15"])


def test_age_group_shares_over_band_rowsum_default():
    # No population column -> denominator is the sum of the named band counts,
    # so the bands must be EXHAUSTIVE (partition the whole population) for the
    # shares to be meaningful. Here young+mid+old cover everyone.
    df = pd.DataFrame({"young": [20.0], "mid": [60.0], "old": [20.0]})
    out = age_group_shares(
        df,
        bands={"share_u15": ["young"], "share_mid": ["mid"], "share_ge65": ["old"]},
    )
    assert out.loc[0, "share_u15"] == 0.2
    assert out.loc[0, "share_ge65"] == 0.2
    # A partition's shares sum to 1.
    assert out.loc[0, ["share_u15", "share_mid", "share_ge65"]].sum() == 1.0


def test_age_group_shares_treats_suppressed_as_zero():
    df = pd.DataFrame({"pop": [100.0], "young": [np.nan], "old": [30.0]})
    out = age_group_shares(
        df, bands={"share_u15": ["young"], "share_ge65": ["old"]},
        population_col="pop")
    # A single suppressed band count contributes nothing rather than nuking
    # the whole share to NaN (min_count=1 keeps a partial sum).
    assert out.loc[0, "share_u15"] == 0.0
    assert out.loc[0, "share_ge65"] == 0.30


# ---------------------------------------------------------------------------
# A destatis "Gitterdaten" zip bundles the SAME theme at 10 km, 1 km and 100 m
# plus a readme. Taking "the first .csv" silently loaded a coarser grid, whose
# every 100 m join key missed -> an all-NaN covariate that dropped out of the
# regressions and produced an empty vulnerability stratum. Pin the selection.
# ---------------------------------------------------------------------------

def _multi_resolution_zip(theme: str = "Leerstandsquote_in_Gitterzellen") -> bytes:
    """A realistic destatis archive: three grids (coarsest FIRST, as the old
    'first .csv' pick would have taken) plus the readme."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{theme}-Datenzusatzbeschreibung.csv",
                    "Merkmal;Beschreibung\nLeerstandsquote;Anteil in Prozent\n")
        for token, x, y in (("10km", 4045000, 2045000),
                            ("1km", 4004500, 2004500),
                            ("100m", 4050, 2050)):
            zf.writestr(
                f"{theme}-{token}-Gitter.csv",
                f"GITTER_ID_{token};x_mp_{token};y_mp_{token};Leerstandsquote\n"
                f"CRS3035RES{token}N{y}E{x};{x};{y};7,3\n",
            )
    return buf.getvalue()


def test_load_inspire_csv_zip_selects_the_100m_member(tmp_path):
    zpath = tmp_path / "vacancy.zip"
    zpath.write_bytes(_multi_resolution_zip())

    df = load_inspire_csv_zip(zpath, resolution_m=100)
    assert df.attrs["member"].endswith("-100m-Gitter.csv")
    assert df.attrs["resolution_m"] == 100.0
    # The 100 m row, not the 10 km one the old "first .csv" pick would take.
    assert (df.loc[0, "x"], df.loc[0, "y"]) == (4050, 2050)
    assert df.loc[0, "Leerstandsquote"] == 7.3
    # The Datenzusatzbeschreibung readme never becomes data.
    assert list(df.columns) == ["x", "y", "Leerstandsquote"]


def test_load_inspire_csv_zip_can_select_a_coarser_member(tmp_path):
    zpath = tmp_path / "vacancy.zip"
    zpath.write_bytes(_multi_resolution_zip())
    df = load_inspire_csv_zip(zpath, resolution_m=1000)
    assert df.attrs["member"].endswith("-1km-Gitter.csv")
    assert df.attrs["resolution_m"] == 1000.0
    # "1km" must not be confused with "10km".
    assert (df.loc[0, "x"], df.loc[0, "y"]) == (4004500, 2004500)


def test_load_inspire_csv_zip_refuses_to_guess_between_grids(tmp_path):
    zpath = tmp_path / "vacancy.zip"
    zpath.write_bytes(_multi_resolution_zip())
    with pytest.raises(ValueError, match="expected exactly 1"):
        load_inspire_csv_zip(zpath)  # no resolution, no member -> no guessing


def test_load_inspire_csv_zip_rejects_a_resolution_mismatch(tmp_path):
    """An explicit member pointing at the wrong grid must fail loudly, not join
    to nothing: this is the guard on the failure mode that emptied the
    ownership/vacancy covariates."""
    zpath = tmp_path / "vacancy.zip"
    zpath.write_bytes(_multi_resolution_zip())
    with pytest.raises(ValueError, match="but sources.ses declares"):
        load_inspire_csv_zip(zpath, member="1km", resolution_m=100)


def test_load_inspire_csv_zip_still_reads_a_single_csv_archive(tmp_path):
    header = "GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner"
    zpath = tmp_path / "pop.zip"
    zpath.write_bytes(_make_inspire_zip(
        "CRS3035RES100mN2000E4000;4050;2050;123", header).getvalue())
    df = load_inspire_csv_zip(zpath)  # unambiguous -> no selector needed
    assert df.loc[0, "Einwohner"] == 123
    # Resolution inferred from the file's own columns, for the join.
    assert df.attrs["resolution_m"] == 100.0


def test_join_warns_when_a_layer_matches_no_cell(capsys):
    # A 1 km layer keyed on the 100 m grid: every key misses. This used to pass
    # silently and produce an empty ses_ column.
    cells = pd.DataFrame({"cell_id": ["a"], "x": [4050.0], "y": [2050.0]})
    coarse = pd.DataFrame({"x": [4004500.0], "y": [2004500.0], "v": [7.3]})
    out = join_ses_to_cells(cells, {"vacancy_rate": coarse})
    assert np.isnan(out.loc[0, "ses_vacancy_rate"])
    assert "matched NO analysis cell" in capsys.readouterr().out


def test_resolution_token_round_trips():
    from depacc.ingest.ses import resolution_token

    assert resolution_token(100) == "100m"
    assert resolution_token(200) == "200m"
    assert resolution_token(1000) == "1km"
    assert resolution_token(10000) == "10km"
