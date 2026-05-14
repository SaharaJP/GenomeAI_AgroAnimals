"""Feeding domain helpers (P1-3b).

Pure functions only: yaml loaders + insight projections.
FastAPI routes live in web_cabinet.api_boundary_v1.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import yaml

from packages.contracts.api_boundary_v1 import FeedingRation, FeedIntakeDrop

logger = logging.getLogger(__name__)

FEED_INSIGHT_TYPES: frozenset[str] = frozenset({
    "feed_intake_drop",
    "dmi_drop",
})


def _read_yaml(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("feeding: failed to read %s: %s", path, exc)
        return None


def load_rations(config_path: Path) -> list[FeedingRation]:
    """Read group rations from a yaml file. Returns [] on any failure or empty config."""
    data = _read_yaml(config_path)
    if not isinstance(data, dict):
        return []
    groups = data.get("groups") or []
    if not isinstance(groups, list):
        return []
    out: list[FeedingRation] = []
    for entry in groups:
        if not isinstance(entry, dict):
            continue
        group_id = entry.get("group_id")
        group_name = entry.get("group_name")
        ration_name = entry.get("ration_name")
        if not group_id or not group_name or not ration_name:
            continue
        out.append(
            FeedingRation(
                group_id=str(group_id),
                group_name=str(group_name),
                ration_name=str(ration_name),
                dm_kg=_to_float(entry.get("dm_kg")),
                last_distribution_at=_to_optstr(entry.get("last_distribution_at")),
                status=str(entry.get("status") or "unknown"),
            )
        )
    return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_optstr(value: Any) -> str | None:
    if value is None:
        return None
    try:
        s = str(value).strip()
        return s or None
    except Exception:
        return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def project_intake_drops(insights: Iterable[Any]) -> list[FeedIntakeDrop]:
    """Filter feed-related insights and project them into FeedIntakeDrop items."""
    out: list[FeedIntakeDrop] = []
    for ins in insights or []:
        try:
            type_ = _get(ins, "type", "")
            if not isinstance(type_, str):
                continue
            if type_ not in FEED_INSIGHT_TYPES:
                continue
            insight_id = _get(ins, "insight_id", "") or _get(ins, "id", "")
            if not insight_id:
                continue
            out.append(
                FeedIntakeDrop(
                    insight_id=str(insight_id),
                    group_id=None,
                    group_name=None,
                    drop_pct=_extract_drop_pct(_get(ins, "chart_data", []) or []),
                    window_days=None,
                    last_observed_at=_to_optstr(_get(ins, "date", None)),
                    title=str(_get(ins, "title", "") or ""),
                )
            )
        except Exception as exc:
            logger.warning("feeding: skip malformed insight in projection: %s", exc)
            continue
    return out


def _extract_drop_pct(chart_data: Iterable[Any]) -> float | None:
    try:
        pts = [float(x) for x in chart_data if isinstance(x, (int, float))]
    except (TypeError, ValueError):
        return None
    if len(pts) < 2 or pts[0] == 0:
        return None
    return (pts[-1] - pts[0]) / pts[0] * 100.0
