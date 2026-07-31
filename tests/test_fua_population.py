"""F.1 — the FUA population table builder (Eurostat urb_lpop1 parsing).

The download + URAU cross-check run on GitHub's runners (workflow "build FUA
population table (F.1)"); these tests pin the pure parsing rules the builder
relies on: latest-reported-year selection, flag stripping, ":" as missing,
legacy LUZ-code mapping and the exclusion of non-FUA spatial codes.
"""

from depacc.ingest.fua_sample import _parse_urb_lpop1, _to_fua_code

TSV = (
    "freq,indic_ur,cities\\TIME_PERIOD\t2020 \t2021 \t2022 \n"
    "A,DE1001V,DE002F\t3100000\t3150000 e\t: \n"      # latest numeric is 2021, flagged
    "A,DE1001V,DE004F\t:\t:\t1080000\n"
    "A,DE1001V,SE001L2\t2200000\t: \t: \n"            # legacy LUZ code
    "A,DE1001V,DE002C\t1800000\t1810000\t1820000\n"   # city code, not a FUA
    "A,DE1002V,DE002F\t1500000\t1520000\t: \n"        # different indicator (male)
    "A,DE1001V,FR001F\t: \t: \t: \n"                  # never reported
)


def test_parse_urb_lpop1_latest_year_flags_and_missing():
    tab = _parse_urb_lpop1(TSV).set_index("code")
    # ":" in 2022 is skipped, the "e" flag on 2021 is stripped.
    assert tab.loc["DE002F", "year"] == 2021
    assert tab.loc["DE002F", "population"] == 3150000
    assert tab.loc["DE004F", "year"] == 2022
    assert tab.loc["DE004F", "population"] == 1080000
    # A code with no numeric observation in any year yields no row at all.
    assert "FR001F" not in tab.index
    # Only the requested indicator (total population) is read.
    assert tab.loc["DE002F", "population"] != 1520000


def test_parse_urb_lpop1_empty_and_headers_only():
    empty = _parse_urb_lpop1("freq,indic_ur,cities\\TIME_PERIOD\t2020\n")
    assert empty.empty and list(empty.columns) == ["code", "year", "population"]


def test_to_fua_code_maps_luz_and_rejects_city_codes():
    assert _to_fua_code("DE002F") == "DE002F"
    assert _to_fua_code("SE001L2") == "SE001F"
    assert _to_fua_code("SE001L") == "SE001F"
    assert _to_fua_code("DE002C") is None      # city
    assert _to_fua_code("DE002K1") is None     # greater city
    assert _to_fua_code("DE") is None          # national aggregate
