"""Ingest stage orchestrator: boundary -> population cells -> OSM facilities
-> GTFS (Tier 2) -> demographics/SES (EU census 1 km for every tier, national
fine grids where configured). Cached and provenance-logged; each step writes
parquet under data/derived/<city>/ and is skipped when up to date."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def network_marker_valid(marker: Path) -> bool:
    """True iff the network marker exists AND the .pbf it points to does.

    The marker (``network_pbf_path.txt``) rides in the per-city DERIVED cache,
    but the merged network file it names can live outside every cache on a
    fresh runner — run 30648450890 restored a marker pointing at a path under
    ``~/.cache/r5py`` and the access stage crashed with FileNotFoundError in
    its first minute instead of re-clipping from the cached raw extracts. A
    stale marker means "regenerate" (which also rewrites the marker with the
    fresh path), never "trust": the pointer is not the artifact — the same
    rule the OD provenance sidecars enforce for matrices.
    """
    if not marker.exists():
        return False
    try:
        target = Path(marker.read_text().strip())
    except OSError:
        return False
    if target.exists():
        return True
    print(f"street-network marker {marker} points at a missing file "
          f"({target}) — regenerating from the cached raw extracts")
    return False


def gtfs_list_valid(listing: Path) -> bool:
    """True iff the GTFS list exists, is non-empty and every feed it names
    exists — the same stale-pointer rule as :func:`network_marker_valid`."""
    if not listing.exists():
        return False
    try:
        paths = [p for p in listing.read_text().splitlines() if p]
    except OSError:
        return False
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"GTFS list {listing} names missing feed file(s) {missing} — "
              f"refetching")
        return False
    return bool(paths)


def derived_dir(cfg: dict, city: str, root: Path) -> Path:
    d = root / cfg["output"]["root"] / city
    d.mkdir(parents=True, exist_ok=True)
    return d


def _derive_ses_columns(cfg: dict, cells: pd.DataFrame) -> pd.DataFrame:
    """Post-join SES derivations declared under ``sources.ses.derived``.

    Currently: ``age_shares`` turns the joined raw age-class head-counts into
    population shares (e.g. under-18 / 65-plus) so the vulnerability
    stratification and gradient regressions consume shares, not counts. Missing
    columns are skipped with a warning rather than raising."""
    from depacc.ingest.ses import age_group_shares

    derived = ((cfg.get("sources", {}).get("ses", {}) or {}).get("derived", {}) or {})
    age = derived.get("age_shares")
    if age:
        bands = age.get("bands", {}) or {}
        pop_col = age.get("population_col")
        needed = {c for cols in bands.values() for c in cols}
        if pop_col:
            needed.add(pop_col)
        missing = sorted(c for c in needed if c not in cells.columns)
        if missing:
            print(f"WARNING: age_shares skipped, absent joined columns: {missing}")
        else:
            cells = age_group_shares(cells, bands, pop_col)
            print(f"SES age shares derived: {sorted(bands)}")
    return cells


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
    from depacc.ingest.census import census_layer
    from depacc.ingest.ghs import fetch_population_cells
    from depacc.ingest.gtfs import fetch_gtfs
    from depacc.ingest.osm import extract_facilities, fetch_pbfs, merge_pbfs
    from depacc.ingest.ses import (
        fetch_ses_layers,
        join_ses_to_cells,
        load_inspire_csv_zip,
        ses_join_resolutions,
    )

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
    # Facility source and street network are SEPARATE decisions. Facilities
    # default to Overpass regardless of engine so that switching the routing
    # engine can never silently change the facility set — the engine
    # cross-check (methods.md §7.1) holds facilities fixed for exactly that
    # reason, and the r5 promotion swaps the engine while keeping the same
    # extractions. Set `sources.facilities: pbf` to extract from the network
    # file instead.
    facilities_source = cfg.get("sources", {}).get("facilities") or "overpass"
    # The r5 engine routes over the real street network, so it needs the .pbf
    # whatever the facility source; friction/synthetic never do (unless the
    # facilities themselves come from the pbf).
    needs_network = (cfg["routing"].get("engine") == "r5"
                     or facilities_source == "pbf")
    missing = [s for s in services
               if not (out / f"facilities_{s}.parquet").exists()]

    clipped: list[Path] = []
    if needs_network and not network_marker_valid(out / "network_pbf_path.txt"):
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
        print(f"street network ready: {network_pbf.name}")

    if facilities_source == "overpass":
        if missing:
            from depacc.ingest.overpass import extract_facilities_overpass

            facilities = extract_facilities_overpass(cfg, fua, root, city)
            for service, fac in facilities.items():
                fac.to_parquet(out / f"facilities_{service}.parquet")
                print(f"facilities[{service}] (overpass): {len(fac)}")
    elif facilities_source == "pbf":
        if missing:
            if not clipped:
                # network_pbf_path.txt existed (cache), so the clip loop above
                # was skipped — re-derive the clip list for extraction only.
                from depacc.ingest.osm import clip_pbf

                pbfs = fetch_pbfs(cfg, root)
                pad = 0.1
                minx, miny, maxx, maxy = fua.to_crs("EPSG:4326").total_bounds
                bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)
                raw_osm = root / cfg["output"]["raw_root"] / "osm"
                clipped = [
                    clip_pbf(p, bbox,
                             raw_osm / f"{p.name.removesuffix('.osm.pbf')}_{city}_clip.osm.pbf")
                    for p in pbfs
                ]
            facilities = extract_facilities(clipped, {s: services[s] for s in missing}, cfg, fua)
            for service, fac in facilities.items():
                fac.to_parquet(out / f"facilities_{service}.parquet")
                print(f"facilities[{service}]: {len(fac)}")
    else:
        raise ValueError(f"Unknown sources.facilities '{facilities_source}'")

    _materialise_aliases(cfg, out)

    modes = cfg["routing"].get("modes") or []
    # GTFS is only needed for transit routing (r5). The friction fast path
    # (walk/car) skips it entirely.
    if "transit" in modes:
        feeds = fetch_gtfs(cfg, root, fua)
        (out / "gtfs_paths.txt").write_text("\n".join(map(str, feeds)))
        print(f"GTFS feeds: {[p.name for p in feeds]}")

    # ---- Demographic / SES enrichment -------------------------------------
    # Two levels, joined in one pass so a city can carry both:
    #   * EU-harmonised Eurostat Census 2021 1 km grid — EVERY tier (it is the
    #     declared tier-1 demographics source), gated only on
    #     sources.census.url being configured. This is what makes age /
    #     employment vulnerability available for all cities.
    #   * national fine SES grids (DE Zensus 100 m, ...) — gated on
    #     sources.ses.urls being present, NOT on the routing engine: the
    #     friction fast path needs SES exactly as much as an r5 run does.
    layers: dict[str, pd.DataFrame] = {}
    resolutions: dict[str, float] = {}

    # The census archive is continental, so the FUA-clipped layer is cached per
    # city: a stage re-dispatch (fresh runner, cache hit on cells.parquet)
    # should not re-parse millions of rows.
    census_cache = out / "census_cells.parquet"
    if census_cache.exists():
        census = pd.read_parquet(census_cache)
        print(f"census 1 km grid cached: {len(census)} cells over the FUA")
    else:
        census = census_layer(cfg, root, fua)
        if census is not None:
            census.to_parquet(census_cache)
    if census is not None:
        layers["census"] = census
        resolutions["census"] = float(
            (cfg.get("sources", {}).get("census", {}) or {}).get("resolution_m", 1000))

    ses_cfg = cfg.get("sources", {}).get("ses", {}) or {}
    if ses_cfg.get("urls"):
        layer_zips = fetch_ses_layers(cfg, root)
        # A destatis "Gitterdaten" zip bundles the SAME theme at 10 km, 1 km and
        # 100 m, so the member is selected by resolution (or by an explicit
        # per-layer substring under sources.ses.members) — never "first .csv".
        # Per-layer resolution overrides handle a theme published only coarser.
        members = ses_cfg.get("members") or {}
        per_layer_res = ses_cfg.get("resolutions") or {}
        default_res = float(ses_cfg.get("resolution_m", 100))
        for name, p in layer_zips.items():
            if name in layers:
                print(f"WARNING: SES layer '{name}' collides with an already "
                      f"joined layer; rename it in sources.ses.layers")
                continue
            want = float(per_layer_res.get(name, default_res))
            layers[name] = load_inspire_csv_zip(
                p, member=members.get(name), resolution_m=want,
                # National grid, one FUA: clip on read (see load_inspire_csv_zip).
                bbox=tuple(fua.total_bounds), pad_m=max(want, 1000.0))
            # The loader reports the resolution it read off the file; trust that
            # over the config so the join always keys on the real grid.
            resolutions[name] = float(layers[name].attrs.get("resolution_m", want))
            print(f"SES layer '{name}': {layers[name].attrs.get('member', '?')} "
                  f"({resolutions[name]:g} m, {len(layers[name])} cells)")

    if layers:
        # Drop every ses_* column carried in from a cached cells.parquet before
        # re-joining. A previous run's columns are not harmless: a release that
        # changes its published columns (or a fix that filters an annotation
        # field) renames them, so stale and fresh names coexist — and
        # equity.ses_covariates defaults to EVERY ses_ column, which would then
        # regress on last week's data under a name nothing produces any more.
        stale = [c for c in cells.columns if c.startswith("ses_")]
        if stale:
            print(f"dropping {len(stale)} ses_* column(s) from the cached cells "
                  f"before re-joining: {stale}")
            cells = cells.drop(columns=stale)
        cells = join_ses_to_cells(cells, layers, resolutions=resolutions)
        cells = _derive_ses_columns(cfg, cells)
        cells.to_parquet(cells_path)
        # Grid resolution per joined layer: which ses_* columns are native
        # 100 m and which are broadcast from a coarser grid (methods.md §6).
        (out / "ses_resolutions.json").write_text(
            json.dumps(ses_join_resolutions(layers, resolutions=resolutions),
                       indent=2),
            encoding="utf-8",
        )
        print(f"SES/demographic layers joined: {sorted(layers)}; "
              f"ses_* columns: "
              f"{sorted(c for c in cells.columns if c.startswith('ses_'))}")
