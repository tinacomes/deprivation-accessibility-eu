# Validation (Workstream E)

Status of the five validation exercises. E.1 (routing-engine cross-check) is
closed and documented in `methods.md` §7.1 and `docs/plan-next-steps.md`
§5.10/§5.15; this page tracks E.2–E.5.

## E.2 — OSM facility completeness vs national registries

Machinery: `depacc completeness --country DE` counts the benchmark services
country-wide via Overpass (`quality.benchmark_osm` — **all** hospitals
(`amenity=hospital`, no `emergency=yes` filter, because the registries count
all hospitals) and all pharmacies) and reports OSM/registry ratios against
`config/registry_counts.csv`. Each registry row carries its `source` and
`year`, so the table is auditable; the current DE rows are:

| service | registry count | source |
|---|---|---|
| hospital | 1 893 (2022) | Statistisches Bundesamt, Grunddaten der Krankenhäuser 2022 — **verify against the current Krankenhausverzeichnis before publication** |
| pharmacy | 17 571 (2023) | ABDA, öffentliche Apotheken, Stand 31.12.2023 — **verify against the current ABDA release** |

Results ([`completeness_DE.csv`](validation/completeness_DE.csv), Overpass
counts of 2026-07-31):

| service | OSM count | registry | ratio | reading |
|---|---|---|---|---|
| pharmacy | 17 156 | 17 571 (2023) | **0.976** | near-complete; part of the residual is real closures since the 2023 registry date |
| hospital | 2 345 | 1 893 (2022) | **1.239** | over-count in the expected direction — OSM maps sites/campuses/clinics where the registry counts institutions |

Reading for the pilot: German OSM shows no under-representation on either
benchmark service, consistent with treating DE as the reference country. The
table also reports the intrinsic `facilities_per_100k` density; once several
countries are benchmarked, each country's density relative to the sample
median becomes the fallback score for countries without a compiled registry
row — that multi-country pass is what should set the
`completeness_threshold` before the full F.2 sample.

Interpretation rule: the ratio can exceed 1 (OSM counts campuses/sites where
a registry counts institutions) — the gate `quality.completeness_threshold`
is about *under*-representation. It stays `null` until enough countries are
benchmarked for the threshold to be set against the observed distribution
rather than a guess; the sampler wiring (`quality/completeness.py
filter_cities`) is in place either way.

## E.3 — external benchmark against published accessibility indicators

Design: compare the pop-weighted travel-time indicators in each city's
`accessibility_by_service.csv` (on `depacc-results`) against published
national accessibility statistics — for Germany, the BBSR/INKAR
Erreichbarkeit indicators (average car/walk time to the nearest supermarket,
pharmacy and GP per municipality). This is a **direction + magnitude** check,
not a calibration: the comparanda differ in population weighting, network,
and facility universe.

Status: open. The BBSR reference values must be pulled from INKAR (not
reachable from the session environment) and recorded here with their
indicator ids and vintage before any comparison is quoted. What can be said
already, from E.1: absolute travel times under the **friction** engine are
understated by 34–314 % by service, so any external comparison of levels must
use the r5 numbers (the primary engine since the promotion).

## E.4 — resolution sanity check (friction vs network QQ)

Implemented inside the engine cross-check: `validation/<city>_engine_qq.csv`
+ `.png` report the population-weighted 1–99 % quantile curves of
`t_regime_everyday` / `t_regime_emergency` under the city's engine vs the
alternative, computed on **uncapped cells only** (both engines), so the
curves compare travel times rather than the finite-fill constant that
dominated the naive scatter (§7.1's capped-lattice caveat). The plan's "~200
random cells" formulation is superseded by the full quantile curves — the
same check without sampling noise. Both files persist to `depacc-results`
under `validation/`. Generated on the next `engine-check` dispatch per city.

## E.5 — face validation

One page per anchor city annotating the published maps against known
geography: [`face-validation-hamburg.md`](face-validation-hamburg.md).
The percentile and co-location maps referenced there persist to
`depacc-results` under `cities/<city>/figures/` (added to
`tools/persist_results.py` for exactly this purpose) on each city's next run.
