"""Robustness harness (structured, NOT probabilistic).

Recomputes only STANDARDISED / rank-based targets (Ginis, typology shares,
city rankings, cluster membership, divergence_gap, coupling rho) for each
parameter variant; raw deprivation magnitudes are never tracked.

Layers 1/2 (curvature + form-swap, :mod:`depacc.sensitivity.harness`) are
evaluated on the saved deprivation-free PER-SERVICE travel times
(``t_eff_<service>`` / ``t_nearest_<service>``): each variant's g is applied
per service and composited with the pipeline's own weighted row mean, so the
baseline row reproduces ``cityplane_row.csv``. No re-routing is needed and —
the typology being rank-based — the variants cannot move the class shares. Layer 3 (accessibility, :mod:`depacc.sensitivity.access`,
``depacc sensitivity --layer access``) sweeps the knobs that build those travel
times (soft-min kappa, 2SFCA gamma, catchment bandwidth, k_nearest, nearest-
only, unreachable treatment, everyday mode set); its cheap variants recompute
the everyday surface from the SAVED OD parquets — still no re-routing — and DO
move the HH share, rho and Ginis. Expensive Layer-3 variants (per-variant
re-routing: friction vs r5, transit) are deferred.
"""

from depacc.sensitivity.access import (  # noqa: F401
    acceptance_table,
    expand_access_variants,
    run_access_sensitivity,
)
from depacc.sensitivity.harness import (  # noqa: F401
    city_stable_targets,
    expand_variants,
    flip_cells,
    rank_agreement_from_tables,
    run_sensitivity,
    variant_regime_deprivations,
)
