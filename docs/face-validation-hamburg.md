# Face validation — Hamburg (E.5)

The test: do the published surfaces trace structure that is *known* about
Hamburg's geography, independent of the model? Each check names the feature,
where it must appear, and what seeing (or not seeing) it means. The maps are
the persisted copies on the `depacc-results` branch
(`cities/hamburg/figures/`, refreshed on every Hamburg run):

- everyday percentile surface: `figures/percentile_everyday.png`
  (+ `percentile_everyday_core.png`, a core zoom (±15 km default, `viz.core_half_m` per city) around the population-weighted
  centre — checks 2 and 5 are unreadable at FUA scale)
- emergency percentile surface: `figures/percentile_emergency.png`
  (+ `_core` variant)
- co-location typology at p50: `figures/compounding_map_50.png`
  (+ `_core` variant, and `compounding_classes_50.png` — one panel per class
  over a grey context, for tracing a single class as a shape: the HL ring of
  check 3, the HH belt of check 4)

Colour key (fixed after the first face-validation pass): **white** = no
populated 100 m cell; **grey** = populated cell with no value/class
(off-network); low deprivation is a visible light tint, never white — the
first-generation maps faded to white at the low end, which made "least
deprived" indistinguishable from "no cell" and check 2 unanswerable.

> Raw links (render on GitHub once the figures have been persisted by a
> post-merge Hamburg run):
> `https://raw.githubusercontent.com/tinacomes/deprivation-accessibility-eu/depacc-results/cities/hamburg/figures/percentile_everyday.png`
> and siblings.

## Checks

1. **The Elbe as an emergency-access barrier.** Fixed river crossings
   (the Elbtunnel/A7 and the city bridges) concentrate car routings, so the
   *emergency* percentile surface south of the river should read worse than
   equally-central areas north of it, with the gradient strongest between
   crossings (Finkenwerder/Altes Land side). If the emergency surface shows
   no north–south asymmetry at all, the car network is not being honoured
   (a friction-raster symptom — under r5 the asymmetry must appear).
2. **Harburg as a secondary centre.** Harburg has its own walkable core
   (GPs, pharmacies, supermarkets around the Rathaus/ring), so the *everyday*
   surface must show a low-deprivation island south of the Elbe, separated
   from the main core by higher-deprivation port/industrial land. An everyday
   surface that paints everything south of the Elbe uniformly deprived is
   reading distance-to-Hamburg-centre, not local walkability.
3. **The rural Kreise ring.** The FUA's commuting zone (Harburg/Stade/
   Pinneberg/Segeberg/Stormarn/Herzogtum Lauenburg fringes) is beyond a
   30-minute walk of most everyday services: the everyday surface should
   saturate high there (the ~12–14 % `pop_share_beyond_everyday_30` mass),
   while the emergency surface stays moderate — car access to an ED remains
   fast far into the ring. This everyday-high/emergency-low contrast is the
   HL class and should dominate the ring on the co-location map.
4. **The compounding (HH) belt.** From §1 of the plan review, the HH class
   should trace the commuter belt — the transition ring between the walkable
   core and the far periphery, plus the between-crossings south: high on
   both percentile surfaces at once, NOT the absolute periphery (which is
   HL: walk-deprived but car-served). An HH class sitting in the city core
   or scattered as salt-and-pepper noise would be a red flag.
5. **Blankenese/Elbvororte.** Wealthy low-density villa quarters with sparse
   retail: locally *higher* everyday deprivation than equally-central dense
   quarters — the map should not read "west = good" uniformly.

## Verdict

Per-cell class assignment is engine-sensitive (23.7 % flip share, §5.10), so
the face validation is read on the r5 maps only. Checks 1–3 bear on the
surfaces; 4–5 on the typology.

**First pass (2026-08, on the first-generation figures — to be re-read on
the fixed maps above):**

1. *Elbe barrier*: "somewhat visible, but in the centre not much of a
   barrier." Partially consistent with expectation — the centre is where the
   crossings are (the city bridges and the Elbtunnel), so a weak central
   gradient is what the road network implies; the diagnostic stretch is
   *between* crossings (Finkenwerder / Altes Land side). Re-read on
   `percentile_emergency_core.png`.
2. *Harburg core*: **not judgeable on the first-generation map** — low
   deprivation rendered white and was indistinguishable from no-cell. This
   was the finding that triggered the colour fix. Re-read.
3. *Rural HL ring*: not clearly visible on the combined map — re-read on the
   HL panel of `compounding_classes_50.png`, which isolates it.
4. *HH belt*: no clear transition visible — same re-read on the HH panel.
   If the belt still fails to appear there, that is a genuine finding
   against the commuter-belt hypothesis, not a viz artefact.
5. *Blankenese*: not resolvable at FUA scale — re-read on
   `percentile_everyday_core.png`.

Net: one genuine partial confirmation (1), one viz defect fixed (2), three
checks deferred to the purpose-built figures (3–5).
