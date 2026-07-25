# Data sources

**No raw data is committed.** Everything below is downloaded by
`depacc run --city <id> --stage ingest` into `data/raw/`, with a JSON
provenance sidecar (`*.provenance.json`: URL, SHA-256, bytes, retrieval
timestamp, licence) written next to every file. Derived artefacts land in
`data/derived/` and are versioned by hash with DVC.

## Tier 1 — continental, harmonised

| Source | What | URL | Licence | Resolution | Native CRS |
|---|---|---|---|---|---|
| JRC GHSL **GHS-POP** R2023A | residential population grid | https://ghsl.jrc.ec.europa.eu/download.php?ds=pop | CC-BY 4.0 | 100 m | Mollweide (ESRI:54009) |
| JRC GHSL **GHS-UCDB** R2024A | Urban Centre Database / Degree of Urbanisation | https://ghsl.jrc.ec.europa.eu/ghs_ucdb_2024.php | CC-BY 4.0 | vector | WGS84 (EPSG:4326) |
| Eurostat/GISCO **URAU 2021** | Eurostat-OECD Functional Urban Area boundaries | https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/urban-audit | Eurostat standard reuse (CC-BY 4.0) | vector | EPSG:3035 / 4326 |
| Eurostat **Census 2021 grid** | EU-wide 1 km demographics (GEOSTAT successor): total population, sex, broad age (< 15 / 15–64 / ≥ 65), employed persons (voluntary), country of birth, prior residence — the 13 variables of EU Reg. 2018/1799. Ingested by `ingest/census.py`; download URL, CSV member, id column and variable codes all live in `sources.census` (`config/defaults.yaml`, flagged `verify: TODO` — confirm against the landing page below before publishing numbers) | landing page: https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids · files: https://gisco-services.ec.europa.eu/census/2021/ and https://gisco-services.ec.europa.eu/pub/population-grid/2021/ | CC-BY 4.0 (© European Union) | 1 km (**broadcast** onto the 100 m analysis grid — see methods.md §6.1) | EPSG:3035, INSPIRE `GRD_ID` |
| **OpenStreetMap** (Geofabrik extracts) | street network + facilities | https://download.geofabrik.de/ | ODbL 1.0 | vector | EPSG:4326 |
| Weiss et al. 2020 **motorised friction surface** (optional robustness) | global travel-friction raster | https://malariaatlas.org/project-resources/accessibility-to-healthcare/ | CC-BY 4.0 | 1 km (30 arc-sec) | EPSG:4326 |

## Tier 2 — deep-dive enrichment

| Source | What | URL | Licence | Resolution | Native CRS |
|---|---|---|---|---|---|
| **GTFS** feeds | public-transit timetables (per city, URLs in `config/cities/*.yaml`) | DE: https://gtfs.de · FR: https://transport.data.gouv.fr · NL: https://gtfs.ovapi.nl · aggregators: Mobility Database / Transitland | per feed (mostly CC-BY / open) | timetable | n/a |
| DE **Zensus 2022** 100 m grid | population, age, household size, net rent, ownership, vacancy (INSPIRE CSVs) | https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/_inhalt.html | dl-de/by-2-0 | 100 m | EPSG:3035 |
| NL **CBS vierkantstatistieken** | 100 m socio-demographic grid | https://www.cbs.nl/nl-nl/dossier/nederland-regionaal/geografische-data/kaart-van-100-meter-bij-100-meter-met-statistieken | CC-BY 4.0 | 100 m | EPSG:28992 |
| FR **INSEE Filosofi** | 200 m gridded income/household data | https://www.insee.fr/fr/statistiques/7655511 | Licence Ouverte 2.0 | 200 m | EPSG:3035 |
| UK **LSOA + IMD 2019** | small-area deprivation index | https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019 | OGL v3 | LSOA | EPSG:27700 |

## Registries used for OSM completeness benchmarking (quality/)

Per-country hospital/pharmacy registry counts vs OSM extraction counts; the
registry list (e.g. DE Krankenhausverzeichnis, national pharmacy chambers) is
recorded in `quality/` outputs with per-source provenance as they are added.

## Processing conventions

- Analysis CRS: **ETRS89 / LAEA Europe (EPSG:3035)**; optional per-city UTM
  for local routing accuracy (`crs.local` in city configs).
- One harmonised city definition for all countries: Eurostat-OECD FUA,
  cross-checked with GHS-UCDB urban centres.
- Attribution: analyses and maps contain data © OpenStreetMap contributors,
  © European Union (Eurostat/GISCO, JRC/GHSL), © Statistische Ämter des
  Bundes und der Länder, and the respective transit agencies.
