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

**Done for the everyday side** (reference data: a manual INKAR export
supplied 2026-08-03, archived verbatim as
[`validation/inkar_erreichbarkeit_2023.csv`](validation/inkar_erreichbarkeit_2023.csv);
the automated downloads were corrupt at the time). Comparanda differ in
scope on purpose — INKAR reports the population-weighted mean **street
distance** to the nearest facility for the **core city** (Kreisfreie Stadt,
2023, BBSR Erreichbarkeitsmodell); ours is the population-weighted mean
**walk time** over the whole **FUA** (r5, 4.8 km/h ⇒ 80 m/min conversion) —
so ratios modestly above 1 are the *expected* sign (the FUA adds the
commuting ring the core city excludes).

| city | service | INKAR (m → min) | ours (min, FUA) | ratio |
|---|---|---|---|---|
| Hamburg | supermarket | 419 → 5.2 | 5.8 | 1.11 |
| Hamburg | GP | 410 → 5.1 | 7.0 | 1.36 |
| Hamburg | pharmacy | 543 → 6.8 | 6.8 | 1.00 |
| Hamburg | primary school | 507 → 6.3 | 6.8 | 1.07 |
| Köln | supermarket | 377 → 4.7 | 5.3 | 1.13 |
| Köln | GP | 346 → 4.3 | 6.4 | 1.49 |
| Köln | pharmacy | 487 → 6.1 | 6.4 | 1.06 |
| Köln | primary school | 465 → 5.8 | **3.7** | **0.64** |

Verdict: **direction and magnitude both pass** for supermarket, pharmacy
and GP — ratios 1.0–1.5 with the FUA⊃core-city bias in the expected
direction, and the between-city ordering (Köln ≤ Hamburg per service)
agrees between sources. Germany-wide INKAR means (e.g. supermarket 979 m ≈
12 min) sit far above both cities, as they must — the Bund value averages
over rural Germany.

**The one anomaly was a catch — and it is RESOLVED: Köln's facility cache
was stale-inflated.** The 0.64× school ratio was impossible if both sources
measured the same facility universe, and it didn't: the cached Köln
extraction carried 2 884 primary schools, 5 593 green spaces and **185
emergency departments** — 3–8× inflated against any plausible count (Hamburg,
a 1.4× larger FUA: 1 120 / 2 030 / 27). On 2026-08-03 a cache eviction
forced a fresh Overpass extraction under the current rules, which returned
**871 schools, 874 greens, 23 EDs** — Hamburg-consistent — and the school
comparison now *passes*: 5.20 min vs INKAR 5.81 ⇒ **ratio 0.89** (and
supermarket moves to 4.68 ⇒ 0.99). Every Köln surface on `depacc-results`
was rebuilt on the corrected set the same day; earlier Köln levels
(including the pilot row of 2026-07-31 and the E.1 absolute levels) carried
the inflated set. E.1's *engine* verdict survives — it held facilities
fixed across engines by construction, so the friction-vs-r5 deltas compared
like with like.

**The policy lesson (binding for the 67-city batch):** the facility
extraction *date* is part of the model. Per-city Overpass caches from
different eras make cities non-comparable — Köln's stale cache survived
several reruns precisely because caching treats extraction as immutable.
Before any comparative batch, extractions should be refreshed to a common
OSM snapshot week (Hamburg's cache, from 2026-07-22, is next in line), and
the extraction date from the provenance sidecar belongs alongside every
cross-city figure. The emergency side of the INKAR comparison stays open
(no hospital car-time indicator retrievable).

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
