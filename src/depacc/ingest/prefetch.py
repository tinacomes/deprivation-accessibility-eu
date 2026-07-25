"""Prefetch the raw sources that are NOT city-specific.

Several inputs are national or continental: one file serves every city in the
sample. The Zensus 2022 grids cover all of Germany (3.09 M 100 m cells per
theme), the Eurostat census grid covers the whole EU, and the GISCO URAU
boundary layer is a single continental file. Each is already downloaded once per
*checkout* — `data/raw/<source>/` is not city-scoped — but a many-city CI batch
fans out over one runner per city, so without a shared cache each runner fetches
the same national file again.

This module names the shared set so a batch can populate it ONCE, in a prep job,
before the per-city matrix starts:

    depacc prefetch --city hamburg --city koeln     # or --all-cities

City-specific raw data (per-FUA friction windows, Overpass extracts, clipped
OSM, GTFS) is deliberately not touched here — it cannot be shared and belongs in
the per-city cache.
"""

from __future__ import annotations

from pathlib import Path

# Raw sub-directories whose contents are identical for every city, and so belong
# in a shared CI cache rather than a per-city one. Keep in sync with the cache
# steps in .github/workflows/*.yml.
SHARED_RAW_DIRS = ("boundaries", "census", "ghs", "ses")
# ...and the per-city ones, for the same reason (documented, not used here).
CITY_RAW_DIRS = ("friction", "gtfs", "osm", "overpass")


def prefetch_shared(cities: list[str], root: Path,
                    config_dir: Path | None = None) -> dict[str, list[str]]:
    """Download the shared national/continental sources for ``cities``.

    Returns ``{source: [what was fetched]}``. Failures are reported and skipped,
    never raised: a prep job that cannot reach one source must not block the
    batch — the per-city runs then fetch what they can and degrade with their own
    warnings.
    """
    from depacc.config import load_config
    from depacc.ingest.boundaries import fetch_fua_boundary
    from depacc.ingest.census import fetch_census_grid
    from depacc.ingest.ghs import GHS_LICENCE, _tile_url, resolve_tiles
    from depacc.ingest.ses import fetch_ses_layers
    from depacc.provenance import download

    done: dict[str, list[str]] = {"boundaries": [], "census": [], "ses": [],
                                  "ghs": []}
    seen_census: set[tuple[str, ...]] = set()
    seen_ses: set[tuple[str, ...]] = set()
    seen_tiles: set[str] = set()

    for city in cities:
        cfg = load_config(city, config_dir=config_dir)
        if cfg["city"].get("synthetic"):
            print(f"prefetch[{city}]: synthetic fixture, nothing to download")
            continue
        label = f"{city} ({cfg['city'].get('country', '??')})"

        # The URAU layer is one continental file; fetching the boundary also
        # warms it, and we need the geometry for the GHS tile resolution below.
        try:
            fua = fetch_fua_boundary(cfg, root)
            done["boundaries"].append(city)
        except Exception as err:  # noqa: BLE001 - a prep job never blocks
            print(f"WARNING: prefetch[{label}] boundary failed: {err}")
            fua = None

        # One EU-wide census archive serves every city: fetch it once.
        census_urls = tuple(sorted(
            [(cfg.get("sources", {}).get("census", {}) or {}).get("url") or ""]
            + list(((cfg.get("sources", {}).get("census", {}) or {})
                    .get("urls") or {}).values())))
        if any(census_urls) and census_urls not in seen_census:
            seen_census.add(census_urls)
            for name, path in fetch_census_grid(cfg, root).items():
                done["census"].append(f"{name}={path.name}")

        # One set of national SES grids per COUNTRY, not per city.
        ses_urls = tuple(sorted(((cfg.get("sources", {}).get("ses", {}) or {})
                                 .get("urls") or {}).values()))
        if ses_urls and ses_urls not in seen_ses:
            seen_ses.add(ses_urls)
            try:
                done["ses"].extend(sorted(fetch_ses_layers(cfg, root)))
            except Exception as err:  # noqa: BLE001
                print(f"WARNING: prefetch[{label}] SES layers failed: {err}")

        # GHS-POP tiles are shared by every city they cover (a DE/NL/BE batch
        # mostly lands in the same two or three tiles).
        if fua is not None:
            try:
                for tile in resolve_tiles(fua, cfg, root):
                    if tile in seen_tiles:
                        continue
                    seen_tiles.add(tile)
                    download(_tile_url(tile),
                             root / cfg["output"]["raw_root"] / "ghs"
                             / f"ghs_pop_{tile}.zip",
                             licence=GHS_LICENCE,
                             note=f"GHS-POP 2020 tile {tile}")
                    done["ghs"].append(tile)
            except Exception as err:  # noqa: BLE001
                print(f"WARNING: prefetch[{label}] GHS tiles failed: {err}")

    for source, items in done.items():
        print(f"prefetch[{source}]: {len(items)} item(s) "
              f"{sorted(set(items)) if items else ''}")
    return done


def configured_cities(config_dir: Path | None = None) -> list[str]:
    from depacc.config import CONFIG_DIR

    cdir = Path(config_dir) if config_dir else CONFIG_DIR
    return sorted(p.stem for p in (cdir / "cities").glob("*.yaml"))
