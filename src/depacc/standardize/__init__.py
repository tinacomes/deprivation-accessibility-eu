"""Enforcement primitive for cross-regime comparability.

Everyday (bounded logistic DLF) and emergency (unbounded Box-Cox DCF)
surfaces live on incomparable scales. Raw magnitudes must NEVER be summed,
differenced, co-plotted on a shared scale, or fed together into clustering.
This module is the single choke point: a `RegimeSurface` that carries its
`scale_state`, population-weighted `to_percentile` / `to_zscore` transforms,
and `require_standardised` guards that any cross-regime consumer calls first.
The guard is the contract — there is deliberately no bypass flag.
"""

from depacc.standardize.surface import (  # noqa: F401
    RegimeSurface,
    max_tie_pop_share,
    require_percentile,
    require_same_standardised,
    require_standardised,
    to_percentile,
    to_zscore,
)
