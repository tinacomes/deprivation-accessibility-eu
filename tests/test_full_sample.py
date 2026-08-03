"""F.2 — the committed full-sample draw (config/full_sample.csv).

The sample is a *study artifact*: the committed CSV is the reviewable object
and the seeded draw must reproduce it exactly, forever. These tests pin that,
plus the design properties the power calculation and the §5.7 covariate
constraint rely on, plus config coverage for every sampled city.
"""

from pathlib import Path

import pandas as pd
import pytest
import yaml

from depacc.config import CONFIG_DIR, load_config
from depacc.ingest.fua_sample import draw_region_strata

SAMPLE_CSV = CONFIG_DIR / "full_sample.csv"


@pytest.fixture(scope="module")
def sample():
    return pd.read_csv(SAMPLE_CSV)


def test_draw_reproduces_the_committed_sample(sample):
    cfg = load_config()
    fuas = pd.read_csv(CONFIG_DIR / "fua_population.csv")
    drawn = draw_region_strata(fuas, cfg)
    pd.testing.assert_frame_equal(
        drawn.reset_index(drop=True),
        sample.reset_index(drop=True),
        check_dtype=False,
    )


def test_design_properties(sample):
    assert len(sample) == 67
    assert sample.fua_code.is_unique
    # Every region-member country with an eligible FUA is represented — the
    # rule that guarantees EL and PT presence (24 of the 26 member countries;
    # AT and CH publish no urb_lpop1 FUA population).
    assert sample.country.nunique() == 24
    # DE+FR cap (census-EMP gap, plan §5.7): imputation bound stays honoured.
    assert int(sample.country.isin(["DE", "FR"]).sum()) <= 12
    # All four regions x all four strata occupied (>5M only where FUAs exist).
    assert set(sample.region) == {"North", "West", "South", "CEE"}
    for region in ("North", "West", "South", "CEE"):
        strata = set(sample[sample.region == region].stratum)
        assert {"100k-250k", "250k-1M", "1M-5M"} <= strata, region
    # Pins: the ten pilot cities, the validity probes, the reviewer pins.
    for code in ("DE002F", "DE004F", "SE001F", "DK002F", "NL001F", "BE002F",
                 "ES001F", "IT005F", "PL001F", "CZ002F",   # pilot
                 "DE084F", "PL010F", "ES010F",             # contrast probes
                 "IT001F", "PT002F",                       # Roma, Porto
                 "EL001F", "PT001F", "NO001F"):            # coverage: EL/PT/NO
        assert code in set(sample.fua_code), code


def test_every_sampled_city_has_a_config(sample):
    by_code = {}
    for p in Path(CONFIG_DIR, "cities").glob("*.yaml"):
        c = yaml.safe_load(p.read_text())
        code = (c.get("city") or {}).get("fua_code")
        if code:
            by_code[code] = p.stem
    missing = [c for c in sample.fua_code if c not in by_code]
    assert not missing, f"sample cities without a config: {missing}"
