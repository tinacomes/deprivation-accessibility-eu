# Per-city compounding maps

One map per city: the **co-location typology at the median split**
(`compounding_map_50.png` from `depacc-results` `cities/<city>/figures/`),
the map whose HH share `cityplane.csv` reports. The legend carries the
class **population** shares; the map itself is area-weighted (methods
§4.1), so the coloured area and the quoted share will not match by eye.

**Read these for spatial pattern, not per-cell class.** ~24 % of
population changes class between routing engines (E.1), so a single
cell's colour is not a finding — the geography of the HH areas is.

Not copied here (they live on `depacc-results` under
`cities/<city>/figures/`, ~30 MB): the percentile surfaces
(`percentile_everyday|emergency.png`), the acute-compounding split
(`compounding_map_75.png`), the class maps and the core-zoom variants.

| city | country | region | population | coverage grade | HH share (p50) | ρ |
|---|---|---|---:|---|---:|---:|
| [Paris](./paris.png) | FR | West | 12,886,280 | covered | 0.334 | 0.50 |
| [Madrid](./madrid.png) | ES | South | 7,601,394 | covered | 0.316 | 0.39 |
| [Barcelona](./barcelona.png) | ES | South | 5,945,709 | covered | 0.309 | 0.36 |
| [Milano](./milano.png) | IT | South | 5,030,024 | covered | 0.319 | 0.37 |
| [Berlin](./berlin.png) | DE | West | 4,875,655 | covered | 0.317 | 0.38 |
| [Roma](./roma.png) | IT | South | 4,432,845 | covered | 0.342 | 0.48 |
| [Athina](./athina.png) | EL | South | 3,522,264 | covered | 0.274 | 0.28 |
| [Bruxelles](./bruxelles.png) | BE | West | 3,521,497 | covered | 0.332 | 0.40 |
| [Napoli](./napoli.png) | IT | South | 3,457,649 | covered | 0.270 | 0.15 |
| [Warszawa](./warszawa.png) | PL | CEE | 3,334,987 | partial desert | 0.347 | 0.49 |
| [Hamburg](./hamburg.png) | DE | West | 3,162,607 | covered | 0.320 | 0.40 |
| [București](./bucuresti.png) | RO | CEE | 3,140,502 | desert | 0.424 | 0.73 |
| [Lisboa](./lisboa.png) | PT | South | 3,132,904 | covered | 0.319 | 0.48 |
| [München](./munchen.png) | DE | West | 3,054,507 | covered | 0.304 | 0.35 |
| [Budapest](./budapest.png) | HU | CEE | 3,030,949 | covered | 0.327 | 0.48 |
| [Amsterdam](./amsterdam.png) | NL | West | 2,829,893 | covered | 0.285 | 0.20 |
| [Stockholm](./stockholm.png) | SE | North | 2,549,795 | partial desert | 0.389 | 0.65 |
| [Köln](./koeln.png) | DE | West | 2,438,338 | covered | 0.312 | 0.36 |
| [Praha](./praha.png) | CZ | CEE | 2,247,160 | covered | 0.354 | 0.46 |
| [København](./kobenhavn.png) | DK | North | 2,180,998 | covered | 0.307 | 0.30 |
| [Sofia](./sofia.png) | BG | CEE | 1,647,936 | partial desert | 0.408 | 0.73 |
| [Helsinki](./helsinki.png) | FI | North | 1,642,879 | covered | 0.270 | 0.26 |
| [Oslo](./oslo.png) | NO | North | 1,550,450 | partial desert | 0.297 | 0.39 |
| [Porto](./porto.png) | PT | South | 1,531,690 | covered | 0.321 | 0.42 |
| [Kraków](./krakow.png) | PL | CEE | 1,350,286 | covered | 0.396 | 0.58 |
| [Katowice](./katowice.png) | PL | CEE | 1,341,890 | covered | 0.267 | 0.10 |
| [Zagreb](./zagreb.png) | HR | CEE | 1,293,698 | partial desert | 0.395 | 0.70 |
| [Antwerpen](./antwerpen.png) | BE | West | 1,219,366 | covered | 0.311 | 0.29 |
| [Rīga](./riga.png) | LV | CEE | 1,110,303 | desert | 0.374 | 0.55 |
| [Bilbao](./bilbao.png) | ES | South | 1,053,444 | covered | 0.324 | 0.42 |
| [Łódź](./lodz.png) | PL | CEE | 1,045,886 | covered | 0.310 | 0.33 |
| [Göteborg](./goteborg.png) | SE | North | 1,042,720 | partial desert | 0.298 | 0.31 |
| [Vilnius](./vilnius.png) | LT | CEE | 1,010,376 | desert | 0.358 | 0.55 |
| [Palermo](./palermo.png) | IT | South | 1,006,055 | partial desert | 0.289 | 0.27 |
| [Alicante](./alicante.png) | ES | South | 996,867 | covered | 0.269 | 0.15 |
| [Wrocław](./wroclaw.png) | PL | CEE | 939,076 | covered | 0.341 | 0.41 |
| [Bratislava](./bratislava.png) | SK | CEE | 931,613 | covered | 0.336 | 0.39 |
| [Ljubljana](./ljubljana.png) | SI | CEE | 919,303 | desert | 0.341 | 0.48 |
| [Palma de Mallorca](./palma_de_mallorca.png) | ES | South | 818,202 | covered | 0.294 | 0.14 |
| [Brno](./brno.png) | CZ | CEE | 745,397 | covered | 0.369 | 0.60 |
| [Tallinn](./tallinn.png) | EE | CEE | 731,883 | desert | 0.326 | 0.45 |
| [Grenoble](./grenoble.png) | FR | West | 688,170 | covered | 0.379 | 0.62 |
| [Luxembourg](./luxembourg.png) | LU | West | 595,677 | partial desert | 0.301 | 0.30 |
| [Toulon](./toulon.png) | FR | West | 540,279 | covered | 0.326 | 0.41 |
| [Aarhus](./aarhus.png) | DK | North | 525,545 | covered | 0.310 | 0.38 |
| [Chemnitz](./chemnitz.png) | DE | West | 481,607 | covered | 0.319 | 0.36 |
| [Turku](./turku.png) | FI | North | 353,992 | partial desert | 0.360 | 0.67 |
| [Stavanger](./stavanger.png) | NO | North | 331,780 | partial desert | 0.299 | 0.28 |
| [Aalborg](./aalborg.png) | DK | North | 309,890 | partial desert | 0.342 | 0.47 |
| [Caserta](./caserta.png) | IT | South | 298,402 | covered | 0.272 | 0.18 |
| [Vicenza](./vicenza.png) | IT | South | 280,054 | covered | 0.344 | 0.47 |
| [Helsingborg](./helsingborg.png) | SE | North | 253,346 | covered | 0.366 | 0.51 |
| [Jaén](./jaen.png) | ES | South | 249,477 | covered | 0.233 | -0.02 |
| [Szeged](./szeged.png) | HU | CEE | 246,224 | covered | 0.392 | 0.58 |
| [Apeldoorn](./apeldoorn.png) | NL | West | 242,638 | covered | 0.333 | 0.33 |
| [Cosenza](./cosenza.png) | IT | South | 239,305 | covered | 0.390 | 0.70 |
| [Brăila](./braila.png) | RO | CEE | 235,919 | partial desert | 0.359 | 0.63 |
| [Amersfoort](./amersfoort.png) | NL | West | 234,650 | covered | 0.282 | 0.26 |
| [Žilina](./zilina.png) | SK | CEE | 217,546 | covered | 0.365 | 0.62 |
| [Västerås](./vasteras.png) | SE | North | 193,510 | covered | 0.387 | 0.62 |
| [Norrköping](./norrkoping.png) | SE | North | 193,317 | partial desert | 0.353 | 0.55 |
| [Lahti](./lahti.png) | FI | North | 191,532 | covered | 0.345 | 0.50 |
| [Landshut](./landshut.png) | DE | West | 168,617 | covered | 0.361 | 0.49 |
| [Sittard-Geleen](./sittard_geleen.png) | NL | West | 165,544 | covered | 0.287 | 0.31 |
| [Arezzo](./arezzo.png) | IT | South | 146,788 | covered | 0.342 | 0.45 |
| [Łomża](./lomza.png) | PL | CEE | 117,255 | partial desert | 0.430 | 0.74 |
| [Talavera de la Reina](./talavera_de_la_reina.png) | ES | South | 101,050 | covered | 0.415 | 0.66 |
