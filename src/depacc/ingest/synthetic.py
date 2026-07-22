"""SYNTHETIC demo city generator — test fixture, NOT data.

Cities whose config sets `city.synthetic: true` get a procedurally generated
monocentric toy city (population blobs + randomly placed facilities) so the
whole pipeline can run end-to-end without any network access — for CI, demos
and development. Every output is watermarked with `synthetic = True`; nothing
here may be mixed into real analyses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_city(cfg: dict) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Return (cells, {service: facilities}) mimicking the ingest outputs."""
    syn = cfg["city"].get("synthetic_params", {}) or {}
    seed = int(syn.get("seed", 7))
    n_side = int(syn.get("n_side", 40))          # n_side x n_side 100m cells
    rng = np.random.default_rng(seed)

    # --- population: dense centre + secondary blob + sparse periphery -------
    ix, iy = np.meshgrid(np.arange(n_side), np.arange(n_side))
    x = ix.ravel() * 100.0
    y = iy.ravel() * 100.0
    centre = (n_side * 50.0, n_side * 50.0)
    blob = (n_side * 25.0, n_side * 75.0)
    d0 = np.hypot(x - centre[0], y - centre[1])
    d1 = np.hypot(x - blob[0], y - blob[1])
    pop = 400 * np.exp(-(d0 / (n_side * 18.0)) ** 2) + 150 * np.exp(-(d1 / (n_side * 10.0)) ** 2)
    pop = pop * rng.uniform(0.5, 1.5, size=pop.size)
    pop = np.where(pop < 2.0, 0.0, pop)
    cells = pd.DataFrame({
        "cell_id": np.arange(x.size),
        "x": x, "y": y,
        "lon": x / 1000.0, "lat": y / 1000.0,   # nominal degrees for demo only
        "population": pop.round(1),
    })
    cells = cells[cells.population > 0].reset_index(drop=True)

    # SES gradient for equity demos: income falls with distance from centre
    # plus noise (purely synthetic).
    cells["ses_income"] = (
        3000 - 1.5 * np.hypot(cells.x - centre[0], cells.y - centre[1]) / 10
        + rng.normal(0, 150, len(cells))
    ).round(0)

    # --- facilities ---------------------------------------------------------
    def _place(n: int, spread: float, capacity: float = 1.0) -> pd.DataFrame:
        # More facilities near the centre (spread<1 pulls them in).
        fx = centre[0] + rng.normal(0, n_side * 100 * spread / 4, n)
        fy = centre[1] + rng.normal(0, n_side * 100 * spread / 4, n)
        fx = np.clip(fx, 0, (n_side - 1) * 100)
        fy = np.clip(fy, 0, (n_side - 1) * 100)
        return pd.DataFrame({
            "lon": fx / 1000.0, "lat": fy / 1000.0,
            "x": fx, "y": fy,
            "capacity": capacity, "capacity_proxy": True,
        })

    counts = {
        "gp": 25, "pharmacy": 18, "supermarket": 22,
        "school_primary": 15, "green_space_local": 12,
        "emergency_dept_hospital": 3, "ambulance_station": 5,
    }
    spreads = {"emergency_dept_hospital": 0.5, "ambulance_station": 0.9}
    # Alias sub-types (extract_alias) are not generated here — the ingest
    # orchestrator materialises them from their parent, so they never consume
    # the RNG and the fixture stays deterministic across config splits.
    from depacc.config import service_extract_aliases

    aliases = service_extract_aliases(cfg)
    facilities = {}
    for service in {**cfg.get("everyday_services", {}), **cfg.get("emergency_services", {})}:
        if service in aliases:
            continue
        n = counts.get(service, 10)
        fac = _place(n, spreads.get(service, 1.0))
        fac["dest_id"] = [f"{service}_{i}" for i in range(len(fac))]
        facilities[service] = fac
    return cells, facilities
