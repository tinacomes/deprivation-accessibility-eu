"""Specification curve over the deprivation-parameter variants."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

from depacc.cityvector.spec_curve import (  # noqa: E402
    load_variant_planes,
    specification_curve,
)

REGION_OF = {f"{r}{i}": r for r in ("A", "B", "C") for i in range(4)}


def _tables(tmp_path, slope=0.05, n_variants=3, partial_city=None):
    """Variant tables for 36 cities (12 countries x 3), gini_everyday scaling
    with population at `slope` per ln pop, plus a per-variant offset."""
    rng = np.random.default_rng(1)
    meta_rows = []
    for country in REGION_OF:
        for i in range(3):
            city = f"{country}_c{i}"
            pop = float(rng.uniform(1e5, 5e6))
            meta_rows.append({"city": city, "country": country,
                              "population": pop})
            rows = []
            variants = [("baseline", "curvature")] + [
                (f"v{j}", "curvature" if j % 2 else "form_swap")
                for j in range(1, n_variants)]
            if partial_city == city:
                variants = variants[:-1]   # this city misses the last variant
            for name, axis in variants:
                base = 0.05 * np.log(pop) * (slope / 0.05) + rng.normal(0, 0.02)
                rows.append({
                    "city": city, "axis": axis, "variant": name,
                    "layer": axis, "threshold": 0.5,
                    "gini_everyday": float(np.exp(np.log(0.05) + base)),
                    "gini_emergency": float(rng.uniform(0.3, 0.5)),
                    "divergence_gap": float(rng.normal(0, 0.1)),
                    "share_LL": 0.25, "share_LH": 0.25,
                    "share_HL": 0.25, "share_HH": 0.25,
                })
            pd.DataFrame(rows).to_csv(
                tmp_path / f"{city}_deprivation_sensitivity.csv", index=False)
    return pd.DataFrame(meta_rows)


def test_curve_covers_every_variant_and_recovers_the_slope(tmp_path):
    meta = _tables(tmp_path, slope=0.06)
    planes = load_variant_planes(tmp_path)
    curve = specification_curve(planes, meta, REGION_OF, n_perm=99)
    ev = curve[(curve.outcome == "gini_everyday")]
    assert set(ev.variant) == {"baseline", "v1", "v2"}
    # Every variant's regression recovers a clearly positive slope.
    assert (ev.elasticity > 0.03).all() and (ev.p < 0.05).all()
    # divergence_gap rides only as a regional permutation contrast.
    dg = curve[curve.outcome == "divergence_gap"]
    assert dg.elasticity.isna().all()
    assert dg.p_regional_permutation.between(0, 1).all()


def test_partial_variant_is_dropped_not_estimated_on_fewer_cities(tmp_path):
    """A variant absent for one city must be dropped entirely — a curve point
    estimated on a different sample is not comparable to its neighbours."""
    meta = _tables(tmp_path, partial_city="A0_c0")
    planes = load_variant_planes(tmp_path)
    assert "v2" not in set(planes.variant)
    curve = specification_curve(planes, meta, REGION_OF, n_perm=99)
    assert set(curve[curve.outcome == "gini_everyday"].variant) == {
        "baseline", "v1"}
