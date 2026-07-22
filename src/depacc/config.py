"""Configuration loading, merging and validation.

Layered YAML: config/defaults.yaml + config/services.yaml +
config/deprivation.yaml, deep-merged with config/cities/<city>.yaml on top.

Deprivation parameters are transferred from the literature and ship as null
placeholders; :func:`require_params` refuses to hand out a parameter set that
still contains nulls, repeating the config's `source` citation so the error
names the exact paper the value must come from.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

GLOBAL_FILES = ("defaults.yaml", "services.yaml", "deprivation.yaml")


class ConfigError(RuntimeError):
    """Invalid or incomplete configuration."""


class MissingParameterError(ConfigError):
    """A literature-transferred parameter is still a null placeholder."""


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict:
    """Recursively merge ``override`` into ``base`` (override wins; dicts merge,
    everything else replaces)."""
    merged = dict(copy.deepcopy(base))
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        content = yaml.safe_load(fh)
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigError(f"Top level of {path} must be a mapping")
    return content


def load_config(city: str | None = None, config_dir: Path | None = None) -> dict:
    """Load the merged configuration, optionally layered with a city file.

    ``city`` is the city id, matching ``config/cities/<city>.yaml``.
    """
    cdir = Path(config_dir) if config_dir else CONFIG_DIR
    cfg: dict = {}
    for name in GLOBAL_FILES:
        cfg = deep_merge(cfg, _load_yaml(cdir / name))
    if city is not None:
        city_path = cdir / "cities" / f"{city}.yaml"
        cfg = deep_merge(cfg, _load_yaml(city_path))
    return cfg


def _find_nulls(params: Mapping[str, Any]) -> list[str]:
    return [k for k, v in params.items() if v is None]


def require_params(spec: Mapping[str, Any], context: str = "deprivation function") -> dict:
    """Return ``spec['params']`` after verifying no value is a null placeholder.

    Raises :class:`MissingParameterError` whose message repeats the spec's
    ``source`` citation, so the error names the paper each parameter must be
    transferred from.
    """
    params = spec.get("params")
    if not isinstance(params, Mapping) or not params:
        raise MissingParameterError(
            f"No parameters configured for {context}. "
            f"Required literature source: {spec.get('source', 'MISSING source field')}"
        )
    nulls = _find_nulls(params)
    if nulls:
        raise MissingParameterError(
            f"Parameter(s) {nulls} for {context} are null placeholders. "
            f"Transfer them from the literature — do not invent values. "
            f"Source: {spec.get('source', 'MISSING source field')}"
        )
    return {k: float(v) for k, v in params.items()}


def deprivation_spec(cfg: Mapping[str, Any], regime: str, alternative: str | None = None) -> dict:
    """Fetch the deprivation-function spec for ``regime`` ('everyday' |
    'emergency'), or a named entry from ``deprivation.alternatives``."""
    dep = cfg.get("deprivation")
    if not isinstance(dep, Mapping):
        raise ConfigError("Config has no 'deprivation' section")
    if alternative is not None:
        alts = dep.get("alternatives") or {}
        if alternative not in alts:
            raise ConfigError(
                f"Unknown deprivation alternative '{alternative}'. "
                f"Available: {sorted(alts)}"
            )
        return dict(alts[alternative])
    if regime not in ("everyday", "emergency"):
        raise ConfigError(f"Unknown regime '{regime}'")
    if regime not in dep:
        raise ConfigError(f"Config deprivation section has no '{regime}' spec")
    return dict(dep[regime])


def everyday_service_spec(cfg: Mapping[str, Any], service: str,
                          alternative: str | None = None) -> dict:
    """Everyday deprivation-function spec for a *specific* service.

    The everyday regime tolerates different travel times per service (a
    pharmacy is near-daily, a secondary school is not), so ``t0`` (and ``k``)
    are a per-service mapping rather than a scalar. Behaviour is selected by
    ``deprivation.everyday.threshold_mode``:

    * ``"uniform"`` (default) — every service uses the base
      ``deprivation.everyday`` params (the single-``t0`` model; retained as the
      defended simplification and as the Phase-3 comparison variant).
    * ``"per_service"`` — a service listed under
      ``deprivation.everyday.per_service`` overrides ``t0``/``k``/``Lmax`` from
      its entry (form/kind unchanged); unlisted services fall back to the base.

    Per-service values are TRANSFERRED FROM THE LITERATURE in config and each
    carries its own ``source`` + ``verify`` flag — nothing is hardcoded here,
    and null placeholders are still rejected downstream by
    :func:`require_params`.
    """
    base = deprivation_spec(cfg, "everyday", alternative=alternative)
    if alternative is not None:
        return base
    ev = (cfg.get("deprivation") or {}).get("everyday") or {}
    mode = ev.get("threshold_mode", "uniform")
    if mode == "uniform":
        return base
    if mode != "per_service":
        raise ConfigError(
            f"Unknown deprivation.everyday.threshold_mode {mode!r} "
            "(expected 'uniform' or 'per_service')"
        )
    entry = (ev.get("per_service") or {}).get(service)
    if not entry:
        return base
    spec = dict(base)
    params = dict(base.get("params") or {})
    for key in ("t0", "k", "Lmax"):
        if key in entry:
            params[key] = entry[key]
    spec["params"] = params
    if entry.get("source"):
        spec["source"] = entry["source"]
    return spec


def service_extract_aliases(cfg: Mapping[str, Any]) -> dict:
    """``{alias_service: parent_service}`` declared via ``extract_alias``.

    A sub-type (e.g. ``school_secondary``) that currently has no OSM extraction
    of its own reuses a parent's facilities and OD matrices — same facilities,
    different deprivation threshold — until a distinguishing extraction (e.g.
    ``isced:level`` for schools, ``min_area_m2`` bands for green space) is
    wired. This keeps the config split honest without routing identical
    facilities twice.
    """
    out: dict = {}
    for key in ("everyday_services", "emergency_services"):
        for svc, spec in (cfg.get(key) or {}).items():
            parent = (spec or {}).get("extract_alias")
            if parent:
                out[svc] = parent
    return out
