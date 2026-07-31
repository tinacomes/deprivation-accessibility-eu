# Face validation — Hamburg (E.5)

The test: do the published surfaces trace structure that is *known* about
Hamburg's geography, independent of the model? Each check names the feature,
where it must appear, and what seeing (or not seeing) it means. The maps are
the persisted copies on the `depacc-results` branch
(`cities/hamburg/figures/`, refreshed on every Hamburg run):

- everyday percentile surface: `figures/percentile_everyday.png`
- emergency percentile surface: `figures/percentile_emergency.png`
- co-location typology at p50: `figures/compounding_map_50.png`

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

To be filled from the first post-merge r5 Hamburg run's persisted figures
(per-cell class assignment is engine-sensitive — 23.7 % flip share, §5.10 —
so the face validation is read on the r5 maps, not the friction ones).
Checks 1–3 bear on the surfaces; 4–5 on the typology. Any failed check gets
its own note here with the map crop and the suspected mechanism.
