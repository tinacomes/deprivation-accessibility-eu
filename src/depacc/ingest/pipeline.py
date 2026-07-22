"""Ingest stage orchestrator: boundary -> population cells -> OSM facilities
-> GTFS (Tier 2) -> SES (Tier 2). Cached and provenance-logged; each step
writes parquet under data/derived/<city>/ and is skipped when up to date."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def derived_dir(cfg: dict, city: str, root: Path) -> Path:
    d = root / cfg["output"]["root"] / city
    d.mkdir(parents=True, exist_ok=True)
    return d


def _materialise_aliases(cfg: dict, out: Path) -> None:
    """Copy each alias service's facilities from its ``extract_alias`` parent.

    A sub-type service (e.g. ``school_secondary``) with no extraction of its
    own reuses the parent's facilities so downstream stages (access,
    deprivation) read the same facilities but apply the sub-type's own
    threshold. Routing is not duplicated — access aliases the OD too."""
    from depacc.config import service_extract_aliases

    for alias, parent in service_extract_aliases(cfg).items():
        parent_path = out / f"facilities_{parent}.parquet"
        alias_path = out / f"facilities_{alias}.parquet"
        if parent_path.exists():
            fac = pd.read_parquet(parent_path)
            fac.to_parquet(alias_path)
            print(f"facilities[{alias}] aliased from '{parent}': {len(fac)}")


def run_ingest(cfg: dict, city: str, root: Path) -> None:
    out = derived_dir(cfg, city, root)

    if cfg["city"].get("synthetic"):
        from depacc.ingest.synthetic import generate_city

        print("SYNTHETIC city fixture — generated, not downloaded; "
              "outputs watermarked synthetic=True")
        cells, facilities = generate_city(cfg)
        cells["synthetic"] = True
        cells.to_parquet(out / "cells.parquet")
        for service, fac in facilities.items():
            fac["synthetic"] = True
            fac.to_parquet(out / f"facilities_{service}.parquet")
        _materialise_aliases(cfg, out)
        print(f"cells: {len(cells)} populated; facilities: "
              f"{ {s: len(f) for s, f in facilities.items()} }")
        return

    from depacc.ingest.boundaries import fetch_fua_boundary
    from depacc.ingest.ghs import fetch_population_cells
    from depacc.ingest.gtfs import fetch_gtfs
    from depacc.ingest.osm import extract_facilities, fetch_pbfs, merge_pbfs
    from depacc.ingest.ses import fetch_ses_layers, join_ses_to_cells, load_inspire_csv_zip

    fua = fetch_fua_boundary(cfg, root)
    fua.to_parquet(out / "fua_boundary.parquet")
    print(f"FUA {cfg['city']['fua_code']}: "
          f"{fua.geometry.area.sum() / 1e6:.0f} km2")

    cells_path = out / "cells.parquet"
    if cells_path.exists():
        cells = pd.read_parquet(cells_path)
        print(f"cells cached: {len(cells)}")
    else:
        cells = fetch_population_cells(fua, cfg, root)
        cells.to_parquet(cells_path)
        print(f"cells: {len(cells)} populated, "
              f"{cells.population.sum() / 1e6:.2f}M people")

    from depacc.config import service_extract_aliases

    aliases = service_extract_aliases(cfg)
    services = {**cfg.get("everyday_services", {}), **cfg.get("emergency_services", {})}
    # Alias services reuse a parent's extraction — never extracted directly.
    services = {s: spec for s, spec in services.items() if s not in aliases}
    facilities_source = (cfg.get("sources", {}).get("facilities")
                         or ("overpass" if cfg["routing"].get("engine") == "friction"
                             else "pbf"))
    missing = [s for s in services
               if not (out / f"facilities_{s}.parquet").exists()]

    if facilities_source == "overpass":
        # Tier-1 fast path: facilities from small Overpass queries; no .pbf
        # download at all (the friction engine needs no street network).
        if missing:
            from depacc.ingest.overpass import extract_facilities_overpass

            facilities = extract_facilities_overpass(cfg, fua, root, city)
            for service, fac in facilities.items():
                fac.to_parquet(out / f"facilities_{service}.parquet")
                print(f"facilities[{service}] (overpass): {len(fac)}")
    else:
        from depacc.ingest.osm import clip_pbf

        pbfs = fetch_pbfs(cfg, root)
        pad = 0.1
        minx, miny, maxx, maxy = fua.to_crs("EPSG:4326").total_bounds
        bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        raw_osm = root / cfg["output"]["raw_root"] / "osm"
        clipped = [
            clip_pbf(p, bbox, raw_osm / f"{p.name.removesuffix('.osm.pbf')}_{city}_clip.osm.pbf")
            for p in pbfs
        ]
        network_pbf = merge_pbfs(
            clipped, raw_osm / f"{city}_merged.osm.pbf"
        )
        (out / "network_pbf_path.txt").write_text(str(network_pbf))
        if missing:
            facilities = extract_facilities(clipped, {s: services[s] for s in missing}, cfg, fua)
            for service, fac in facilities.items():
                fac.to_parquet(out / f"facilities_{service}.parquet")
                print(f"facilities[{service}]: {len(fac)}")

    _materialise_aliases(cfg, out)

    modes = cfg["routing"].get("modes") or []
    # GTFS is only needed for transit routing (r5). The friction fast path
    # (walk/car) skips it entirely.
    if "transit" in modes:
        feeds = fetch_gtfs(cfg, root, fua)
        (out / "gtfs_paths.txt").write_text("\n".join(map(str, feeds)))
        print(f"GTFS feeds: {[p.name for p in feeds]}")

    # SES enrichment (Tier 2), only if download URLs are configured — avoids
    # a wall of skip-warnings when they are not yet set.
    ses_urls = (cfg.get("sources", {}).get("ses", {}) or {}).get("urls")
    if int(cfg["city"].get("tier", 1)) >= 2 and ses_urls:
        layer_zips = fetch_ses_layers(cfg, root)
        if layer_zips:
            layers = {name: load_inspire_csv_zip(p) for name, p in layer_zips.items()}
            cells = join_ses_to_cells(cells, layers)
            cells.to_parquet(cells_path)
            print(f"SES layers joined: {sorted(layer_zips)}")
