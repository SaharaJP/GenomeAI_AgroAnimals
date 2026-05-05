"""Alerts Bridge — facade between alerts_v2 computation engine and web_cabinet UI."""
from __future__ import annotations

from web_cabinet.analytics.cache import cached

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Optional

_DEMO_DATA = Path(__file__).parents[2] / "data" / "demo" / "investor_v1"

_SEVERITY_MAP = {
    "HIGH": "critical",
    "CRITICAL": "critical",
    "MEDIUM": "warning",
    "LOW": "info",
    "INFO": "info",
}

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class ActiveAlert:
    alert_id: str
    farm_id: str
    animal_id: Optional[str]
    alert_type: str
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    detected_at: date
    evidence: dict


def _normalize_severity(raw: str) -> Literal["critical", "warning", "info"]:
    return _SEVERITY_MAP.get(raw.upper(), "warning")  # type: ignore[return-value]


def _dict_to_active_alert(d: dict, farm_id: str, today: date) -> ActiveAlert:
    dk = str(d.get("dedupe_key") or d.get("alert_type") or "unknown")
    alert_id = hashlib.sha1(dk.encode()).hexdigest()[:12]
    raw_sev = str(d.get("severity") or "MEDIUM")
    severity = _normalize_severity(raw_sev)
    animal_id = d.get("object_id") if d.get("object_type") == "animal" else None
    return ActiveAlert(
        alert_id=alert_id,
        farm_id=farm_id,
        animal_id=str(animal_id) if animal_id else None,
        alert_type=str(d.get("alert_type") or "UNKNOWN"),
        severity=severity,
        title=str(d.get("title") or dk),
        description=str(d.get("cause") or ""),
        detected_at=today,
        evidence=d.get("why") or {},
    )


def _alerts_from_health_events(farm_id: str, today: date, data_dir: Path) -> list[ActiveAlert]:
    import pandas as pd

    path = data_dir / "dm_health_events.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    if df.empty:
        return []

    # Tenant isolation: filter by tenant_id or farm_id column when present.
    _tenant_col = next((c for c in ("tenant_id", "farm_id") if c in df.columns), None)
    if _tenant_col:
        df = df[df[_tenant_col] == farm_id]
    if df.empty:
        return []

    out: list[ActiveAlert] = []
    for _, r in df.iterrows():
        event_id = str(r.get("event_id") or "")
        dk = event_id or f"health|{r.get('animal_id')}|{r.get('event_date')}"
        alert_id = hashlib.sha1(dk.encode()).hexdigest()[:12]
        raw_sev = str(r.get("severity") or "medium")
        severity = _normalize_severity(raw_sev)
        animal_id = str(r.get("animal_id") or "") or None
        event_date_raw = r.get("event_date")
        try:
            detected_at = date.fromisoformat(str(event_date_raw))
        except Exception:
            detected_at = today
        event_type = str(r.get("event_type") or "health_event")
        out.append(
            ActiveAlert(
                alert_id=alert_id,
                farm_id=farm_id,
                animal_id=animal_id,
                alert_type=f"HEALTH.{event_type.upper()}",
                severity=severity,
                title=f"Health event: {event_type}",
                description=str(r.get("notes") or event_type),
                detected_at=detected_at,
                evidence={"event_id": event_id, "event_type": event_type, "raw_severity": raw_sev},
            )
        )
    return out


def _filter_raw_by_farm_id(raw: list[dict], farm_id: str) -> list[dict]:
    """Drop generator dicts that belong to a different tenant.

    Keeps dicts that have no tenant field (single-farm generator, backward-compatible)
    and dicts whose tenant_id / farm_id matches the requested farm_id.
    """
    return [
        d for d in raw
        if d.get("tenant_id", farm_id) == farm_id
        and d.get("farm_id", farm_id) == farm_id
    ]


def _load_generators():
    from genomeai.alerts_v2 import (
        generate_from_dm_alerts,
        generate_repro_alerts,
        generate_withdrawal_alerts,
    )
    return generate_from_dm_alerts, generate_withdrawal_alerts, generate_repro_alerts


def list_active_alerts(
    farm_id: str,
    *,
    severity_filter: Optional[list[str]] = None,
    limit: int = 50,
) -> list[ActiveAlert]:
    """Wrapper over alerts_v2. Returns active alerts from DB (demo: from CSV).

    Validation runs before the cache so an empty farm_id always raises.
    """
    if not farm_id:
        raise ValueError("farm_id must not be empty")
    return _list_active_alerts_cached(farm_id, severity_filter=severity_filter, limit=limit)


@cached(ttl=600)
def _list_active_alerts_cached(
    farm_id: str,
    *,
    severity_filter: Optional[list[str]] = None,
    limit: int = 50,
) -> list[ActiveAlert]:
    today = date.today()
    raw: list[dict] = []
    for fn in _load_generators():
        try:
            raw.extend(fn(canonical_dir=_DEMO_DATA, data_version="investor_v1", today=today))
        except Exception:
            pass

    if raw:
        raw = _filter_raw_by_farm_id(raw, farm_id)
        alerts = [_dict_to_active_alert(d, farm_id, today) for d in raw]
    if not raw:
        alerts = _alerts_from_health_events(farm_id, today, _DEMO_DATA)

    alerts.sort(key=lambda a: (_SEVERITY_ORDER.get(a.severity, 99), -a.detected_at.toordinal()))

    if severity_filter:
        normalized_filter = [_normalize_severity(s) for s in severity_filter]
        alerts = [a for a in alerts if a.severity in normalized_filter]

    return alerts[:limit]
