from __future__ import annotations

"""Alert Center v2 - explainable alert generators.

Core rules:
- No AI diagnoses. Only facts, QC issues, ML risk flags, and deterministic business rules.
- Generators must degrade gracefully when data is missing.

Produced alerts are *candidates* (dicts) that the web layer can store + manage lifecycle.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yaml

from core.application import find_latest_qc2_run_dir

from .sensor_anomaly_v1 import DetectorConfig, detect_sensor_anomalies, load_cow_day


CATALOG_PATH = Path("configs/alerts_v2/catalog.yaml")


def _safe_read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _today_iso(today: Optional[date] = None) -> str:
    return (today or date.today()).isoformat()


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    title: str
    source: str
    severity: str
    default_deadline_days: int
    why: str
    actions: List[str]


def load_alert_catalog(path: Path = CATALOG_PATH) -> Dict[str, CatalogEntry]:
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or "types" not in obj:
        raise ValueError("alerts_v2 catalog must be dict with 'types' list")
    types = obj.get("types")
    if not isinstance(types, list):
        raise ValueError("alerts_v2 catalog: 'types' must be a list")
    out: Dict[str, CatalogEntry] = {}
    for t in types:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        if tid in out:
            raise ValueError(f"Duplicate alert type in catalog: {tid}")
        out[tid] = CatalogEntry(
            id=tid,
            title=str(t.get("title") or tid),
            source=str(t.get("source") or "unknown"),
            severity=str(t.get("severity") or "MEDIUM"),
            default_deadline_days=int(t.get("default_deadline_days") or 7),
            why=str(t.get("why") or ""),
            actions=[str(x) for x in (t.get("actions") or [])],
        )
    return out


def validate_catalog_min_types(path: Path = CATALOG_PATH, *, min_types: int = 40) -> None:
    cat = load_alert_catalog(path)
    if len(cat) < min_types:
        raise ValueError(f"alerts_v2 catalog must have >= {min_types} types; got {len(cat)}")


def _deadline_iso(today: date, days: int) -> str:
    return (today + timedelta(days=int(days))).isoformat()


def _mk_candidate(
    cat: Dict[str, CatalogEntry],
    *,
    alert_type: str,
    object_type: str,
    object_id: str,
    cause: str,
    confidence: Optional[float],
    attachments: List[Dict[str, Any]],
    why_kv: Dict[str, Any],
    data_version: Optional[str] = None,
    qc_run: Optional[str] = None,
    model_version: Optional[str] = None,
    scoring_run: Optional[str] = None,
    report_version: Optional[str] = None,
    today: Optional[date] = None,
    dedupe_key: Optional[str] = None,
) -> Dict[str, Any]:
    today = today or date.today()
    c = cat.get(alert_type)
    title = c.title if c else alert_type
    source = c.source if c else "unknown"
    deadline = _deadline_iso(today, c.default_deadline_days) if c else _deadline_iso(today, 7)
    what_to_do = [{"step": i + 1, "text": s} for i, s in enumerate((c.actions if c else []))]
    why = {"summary": (c.why if c else ""), **(why_kv or {})}
    # a deterministic, stable dedupe key
    dk = dedupe_key or f"{alert_type}|{object_type}|{object_id}|{source}"  # stable
    return {
        "alert_type": alert_type,
        "title": title,
        "source": source,
        "cause": cause,
        "confidence": confidence,
        "object_type": object_type,
        "object_id": object_id,
        "deadline": deadline,
        "owner_user_id": None,
        "attachments": attachments or [],
        "why": why,
        "what_to_do": what_to_do,
        "data_version": data_version,
        "qc_run": qc_run,
        "model_version": model_version,
        "scoring_run": scoring_run,
        "report_version": report_version,
        "dedupe_key": dk,
    }


def generate_from_qc2(
    *,
    artifacts_root: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Convert qc2 auto-alerts into Alert Center v2 candidates."""
    today = today or date.today()
    cat = load_alert_catalog()

    run_dir = find_latest_qc2_run_dir(artifacts_root=artifacts_root, data_version=data_version)
    if run_dir is None:
        return []

    qc_run = run_dir.name
    alerts_csv = run_dir / "alerts_auto.csv"
    df = _safe_read_csv(alerts_csv)
    if df is None or df.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        a_type = str(r.get("alert_type") or "QC.GENERIC")
        ent_type = str(r.get("entity_type") or "dataset")
        ent_id = str(r.get("entity_id") or r.get("farm_id") or "")
        if not ent_id:
            ent_id = "unknown"
        msg = str(r.get("message") or "QC issue")
        rule_id = str(r.get("source_rule_id") or "")
        attachments = [
            {"kind": "qc2", "path": str(alerts_csv), "qc_run": qc_run, "rule_id": rule_id},
        ]
        why_kv = {
            "qc_rule_id": rule_id,
            "qc_message": msg,
            "severity": str(r.get("severity") or ""),
        }
        # map QC alert type to catalog id if exists
        alert_type = a_type if a_type in cat else "QC.GENERIC"
        out.append(
            _mk_candidate(
                cat,
                alert_type=alert_type,
                object_type=ent_type,
                object_id=ent_id,
                cause=msg,
                confidence=None,
                attachments=attachments,
                why_kv=why_kv,
                data_version=data_version,
                qc_run=qc_run,
                today=today,
                dedupe_key=f"{alert_type}|{ent_type}|{ent_id}|{rule_id}",
            )
        )
    return out


def generate_from_pedigree_qc(
    *,
    artifacts_root: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Convert pedigree_qc alerts_auto into Alert Center v2 candidates (T6-01).

    Reads: artifacts/<data_version>/pedigree/<pedigree_run>/alerts_auto.csv
    Picks latest run by lexicographic order.
    """
    today = today or date.today()
    cat = load_alert_catalog()

    base = artifacts_root / data_version / 'pedigree'
    if not base.exists():
        return []
    runs = sorted([p for p in base.iterdir() if p.is_dir()])
    if not runs:
        return []
    run_dir = runs[-1]
    ped_run = run_dir.name
    alerts_csv = run_dir / 'alerts_auto.csv'
    df = _safe_read_csv(alerts_csv)
    if df is None or df.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        a_type = str(r.get('alert_type') or 'PEDIGREE.CONFLICT')
        ent_type = str(r.get('entity_type') or 'animal')
        ent_id = str(r.get('entity_id') or r.get('farm_id') or 'unknown')
        msg = str(r.get('message') or 'Pedigree issue')
        rule_id = str(r.get('source_rule_id') or '')
        # keep only known catalog ids; otherwise bucket
        alert_type = a_type if a_type in cat else 'QC.GENERIC'
        attachments = [
            {'kind': 'pedigree_qc', 'path': str(alerts_csv), 'pedigree_run': ped_run, 'rule_id': rule_id},
        ]
        why_kv = {
            'pedigree_rule_id': rule_id,
            'pedigree_message': msg,
            'severity': str(r.get('severity') or ''),
        }
        out.append(
            _mk_candidate(
                cat,
                alert_type=alert_type,
                object_type=ent_type,
                object_id=ent_id,
                cause=msg,
                confidence=None,
                attachments=attachments,
                why_kv=why_kv,
                data_version=data_version,
                qc_run=str(r.get('qc_run') or ped_run),
                today=today,
                dedupe_key=f"{alert_type}|{ent_type}|{ent_id}|{rule_id}",
            )
        )
    return out


def generate_from_dm_alerts(
    *,
    canonical_dir: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Convert existing dm_alerts facts (often ML risks) into v2 alert candidates."""
    today = today or date.today()
    cat = load_alert_catalog()
    df = _safe_read_csv(canonical_dir / "dm_alerts.csv")
    if df is None or df.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        raw_type = str(r.get("alert_type") or "").strip()
        # mapping: preserve known v2 types; otherwise bucket
        if raw_type in cat:
            alert_type = raw_type
        elif raw_type:
            # normalize common legacy risk types
            if "health" in raw_type:
                alert_type = "ML.HEALTH_RISK"
            elif "repro" in raw_type:
                alert_type = "ML.REPRO_RISK"
            else:
                alert_type = "ML.RISK_GENERIC"
        else:
            alert_type = "ML.RISK_GENERIC"

        ent_type = str(r.get("entity_type") or "animal")
        ent_id = str(r.get("entity_id") or r.get("animal_id") or "unknown")
        msg = str(r.get("message") or r.get("reason") or "Risk flag")
        conf = None
        try:
            conf = float(r.get("confidence")) if r.get("confidence") is not None else None
        except Exception:
            conf = None

        attachments = [{"kind": "dm_alerts", "dataset": "dm_alerts", "row_id": str(r.get("alert_id") or "")}]
        why_kv = {
            "raw_alert_type": raw_type,
            "risk_score": r.get("score"),
            "model": r.get("model_version"),
        }
        out.append(
            _mk_candidate(
                cat,
                alert_type=alert_type,
                object_type=ent_type,
                object_id=ent_id,
                cause=msg,
                confidence=conf,
                attachments=attachments,
                why_kv=why_kv,
                data_version=data_version,
                model_version=str(r.get("model_version") or "") or None,
                scoring_run=str(r.get("scoring_run") or "") or None,
                today=today,
                dedupe_key=f"{alert_type}|{ent_type}|{ent_id}|{raw_type}",
            )
        )
    return out


def generate_withdrawal_alerts(
    *,
    canonical_dir: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Business rule alerts from treatments/withdrawal windows."""
    today = today or date.today()
    cat = load_alert_catalog()
    tr = _safe_read_csv(canonical_dir / "dm_treatments.csv")
    if tr is None or tr.empty:
        return []

    # normalize withdrawal end date
    if "withdrawal_end_date" not in tr.columns:
        return []

    tr["withdrawal_end_date"] = pd.to_datetime(tr["withdrawal_end_date"], errors="coerce").dt.date
    tr["animal_id"] = tr.get("animal_id", pd.Series([None] * len(tr)))

    out: List[Dict[str, Any]] = []
    for _, r in tr.iterrows():
        animal_id = str(r.get("animal_id") or "")
        if not animal_id:
            continue
        end = r.get("withdrawal_end_date")
        if not isinstance(end, date):
            continue

        if end >= today:
            # active
            days_left = (end - today).days
            a_type = "WITHDRAWAL.ACTIVE" if days_left > 3 else "WITHDRAWAL.ENDING_SOON"
            cause = f"Withdrawal active until {end.isoformat()} ({days_left}d left)"
            why_kv = {
                "withdrawal_end_date": end.isoformat(),
                "days_left": days_left,
                "drug_code": r.get("drug_code"),
                "treatment_id": r.get("treatment_id"),
            }
            out.append(
                _mk_candidate(
                    cat,
                    alert_type=a_type if a_type in cat else "WITHDRAWAL.ACTIVE",
                    object_type="animal",
                    object_id=animal_id,
                    cause=cause,
                    confidence=None,
                    attachments=[{"kind": "treatment", "dataset": "dm_treatments", "treatment_id": str(r.get("treatment_id") or "")}],
                    why_kv=why_kv,
                    data_version=data_version,
                    today=today,
                    dedupe_key=f"{a_type}|animal|{animal_id}|{end.isoformat()}",
                )
            )
    return out


def generate_repro_alerts(
    *,
    canonical_dir: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Best-effort repro business alerts.

    If dm_repro.csv is present, use simple transparent thresholds:
    - days_open > 150 => REPRO.LONG_DAYS_OPEN
    - services_count >= 3 and not pregnant => REPRO.REPEAT_BREEDER
    Schema is intentionally flexible: generators only trigger when expected columns exist.
    """
    today = today or date.today()
    cat = load_alert_catalog()

    df = _safe_read_csv(canonical_dir / "dm_repro.csv")
    if df is None or df.empty:
        return []

    cols = set(df.columns)
    if "animal_id" not in cols:
        return []

    out: List[Dict[str, Any]] = []
    # long days open
    if "days_open" in cols:
        for _, r in df.iterrows():
            try:
                days_open = float(r.get("days_open"))
            except Exception:
                continue
            if days_open > 150:
                animal_id = str(r.get("animal_id") or "")
                if not animal_id:
                    continue
                out.append(
                    _mk_candidate(
                        cat,
                        alert_type="REPRO.LONG_DAYS_OPEN",
                        object_type="animal",
                        object_id=animal_id,
                        cause=f"Days open high: {int(days_open)} (>150)",
                        confidence=None,
                        attachments=[{"kind": "repro", "dataset": "dm_repro", "animal_id": animal_id}],
                        why_kv={"days_open": int(days_open)},
                        data_version=data_version,
                        today=today,
                        dedupe_key=f"REPRO.LONG_DAYS_OPEN|animal|{animal_id}",
                    )
                )

    # repeat breeder
    if {"services_count", "is_pregnant"}.issubset(cols):
        for _, r in df.iterrows():
            animal_id = str(r.get("animal_id") or "")
            if not animal_id:
                continue
            try:
                sc = int(float(r.get("services_count")))
            except Exception:
                continue
            preg = str(r.get("is_pregnant") or "").strip().lower() in {"1", "true", "yes"}
            if (not preg) and sc >= 3:
                out.append(
                    _mk_candidate(
                        cat,
                        alert_type="REPRO.REPEAT_BREEDER",
                        object_type="animal",
                        object_id=animal_id,
                        cause=f"Repeat breeder risk: services_count={sc} and not pregnant",
                        confidence=None,
                        attachments=[{"kind": "repro", "dataset": "dm_repro", "animal_id": animal_id}],
                        why_kv={"services_count": sc, "is_pregnant": False},
                        data_version=data_version,
                        today=today,
                        dedupe_key=f"REPRO.REPEAT_BREEDER|animal|{animal_id}",
                    )
                )

    return out



def _find_latest_dir(base: Path) -> Optional[Path]:
    if not base.exists():
        return None
    runs = sorted([p for p in base.iterdir() if p.is_dir()])
    return runs[-1] if runs else None


def generate_mastitis_risk_alerts(
    *,
    artifacts_root: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Generate ML.MASTITIS_RISK alerts from latest mastitis scoring output.

    Input: artifacts/<data_version>/mastitis/scoring/<scoring_run>/mastitis_risk_scores.csv
    """
    today = today or date.today()
    cat = load_alert_catalog()

    score_base = artifacts_root / data_version / "mastitis" / "scoring"
    run_dir = _find_latest_dir(score_base)
    if not run_dir:
        return []
    scoring_run = run_dir.name
    scores_csv = run_dir / "mastitis_risk_scores.csv"
    df = _safe_read_csv(scores_csv)
    if df is None or df.empty:
        return []

    # threshold is included in scoring_summary if present
    thr = None
    summary_json = run_dir / "scoring_summary.json"
    if summary_json.exists():
        try:
            s = json.loads(summary_json.read_text(encoding="utf-8"))
            thr = float(s.get("risk_threshold")) if s.get("risk_threshold") is not None else None
        except Exception:
            thr = None
    if thr is None:
        thr = 0.7

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        try:
            flag = int(r.get("risk_flag") or 0)
        except Exception:
            flag = 0
        if flag != 1:
            continue
        animal_id = str(r.get("animal_id") or "")
        if not animal_id:
            continue
        farm_id = str(r.get("farm_id") or "unknown")
        score = r.get("risk_proba")
        conf = None
        try:
            conf = float(score) if score is not None else None
        except Exception:
            conf = None

        why_facts = str(r.get("why_facts") or "")
        cause = f"Высокий риск мастита (N дней). score={conf:.3f} >= {thr:.2f}" if conf is not None else "Высокий риск мастита (N дней)"
        attachments = [
            {"kind": "mastitis_scoring", "path": str(scores_csv), "scoring_run": scoring_run},
        ]
        why_kv = {
            "risk_proba": conf,
            "threshold": thr,
            "why_facts": why_facts,
            "policy": "risk_only_no_diagnosis",
        }
        out.append(
            _mk_candidate(
                cat,
                alert_type="ML.MASTITIS_RISK" if "ML.MASTITIS_RISK" in cat else "ML.HEALTH_RISK",
                object_type="animal",
                object_id=animal_id,
                cause=cause,
                confidence=conf,
                attachments=attachments,
                why_kv=why_kv,
                data_version=data_version,
                scoring_run=scoring_run,
                today=today,
                dedupe_key=f"ML.MASTITIS_RISK|animal|{animal_id}|{scoring_run}",
            )
        )
    return out


def generate_sensor_anomaly_alerts(
    *,
    canonical_dir: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Best-effort sensor anomaly alerts.

    Triggers when:
    - is_anomaly column is truthy OR
    - abs(zscore) >= 3
    Expected flexible schema: animal_id, sensor, timestamp, value.
    """
    today = today or date.today()
    cat = load_alert_catalog()
    df = _safe_read_csv(canonical_dir / "dm_sensor_readings.csv")
    if df is None or df.empty:
        return []
    cols = set(df.columns)
    if "animal_id" not in cols:
        return []

    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        animal_id = str(r.get("animal_id") or "")
        if not animal_id:
            continue
        is_anom = False
        if "is_anomaly" in cols:
            v = str(r.get("is_anomaly") or "").strip().lower()
            is_anom = v in {"1", "true", "yes"}
        z = None
        if "zscore" in cols:
            try:
                z = float(r.get("zscore"))
            except Exception:
                z = None
        if (not is_anom) and (z is None or abs(z) < 3.0):
            continue

        sensor = str(r.get("sensor") or "sensor")
        ts = str(r.get("timestamp") or r.get("ts") or "")
        val = r.get("value")
        cause = f"Sensor anomaly: {sensor} value={val} z={z}" if z is not None else f"Sensor anomaly: {sensor} value={val}"
        out.append(
            _mk_candidate(
                cat,
                alert_type="SENSOR.ANOMALY",
                object_type="animal",
                object_id=animal_id,
                cause=cause,
                confidence=None,
                attachments=[{"kind": "sensor", "dataset": "dm_sensor_readings", "animal_id": animal_id, "timestamp": ts}],
                why_kv={"sensor": sensor, "timestamp": ts, "value": val, "zscore": z},
                data_version=data_version,
                today=today,
                dedupe_key=f"SENSOR.ANOMALY|animal|{animal_id}|{sensor}",
            )
        )

    return out


def generate_sensor_daily_rule_alerts(
    *,
    artifacts_root: Path,
    data_version: str,
    today: Optional[date] = None,
    cfg: DetectorConfig = DetectorConfig(),
) -> List[Dict[str, Any]]:
    """Rule-based (v1) anomaly detector on daily sensor aggregates.

    Source-of-truth for detection is the `cow_day` mart (T3-02). If the mart is missing,
    this generator returns an empty list (best-effort).

    Produced alert types:
      - SENSOR.OFFLINE (data dropout)
      - SENSOR.TEMP_SPIKE (outlier)
      - SENSOR.RUMINATION_DROP (outlier)
      - SENSOR.ACTIVITY_DROP (outlier)
      - SENSOR.BASELINE_DRIFT (drift)
    """
    today = today or date.today()
    cat = load_alert_catalog()

    cow_day = load_cow_day(artifacts_root=artifacts_root, data_version=data_version)
    if cow_day.empty:
        return []

    an = detect_sensor_anomalies(cow_day, cfg=cfg)
    if an.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, r in an.iterrows():
        a_type = str(r.get("anomaly_type") or "")
        metric = str(r.get("metric") or "")
        animal_id = str(r.get("animal_id") or "")
        if not animal_id:
            continue
        farm_id = r.get("farm_id")
        when = r.get("date")
        details = r.get("details_json")
        if not isinstance(details, dict):
            try:
                details = json.loads(details) if details else {}
            except Exception:
                details = {}

        if a_type == "data_dropout":
            alert_type = "SENSOR.OFFLINE"
            cause = "Нет данных сенсоров за последние дни"
            why_kv = {"metric": "sensors", "farm_id": farm_id, "when": str(when), **details}
            dk = f"SENSOR.OFFLINE|animal|{animal_id}"
        elif a_type == "temp_spike":
            alert_type = "SENSOR.TEMP_SPIKE"
            v = details.get("value")
            cause = f"Резкий рост температуры: {v}°C" if v is not None else "Резкий рост температуры"
            why_kv = {"metric": "body_temp_c", "farm_id": farm_id, "when": str(when), **details}
            dk = f"SENSOR.TEMP_SPIKE|animal|{animal_id}"
        elif a_type == "rumination_drop":
            alert_type = "SENSOR.RUMINATION_DROP"
            v = details.get("value")
            cause = f"Падение жвачки: {v} мин" if v is not None else "Падение жвачки"
            why_kv = {"metric": "rumination_min", "farm_id": farm_id, "when": str(when), **details}
            dk = f"SENSOR.RUMINATION_DROP|animal|{animal_id}"
        elif a_type == "activity_drop":
            alert_type = "SENSOR.ACTIVITY_DROP"
            v = details.get("value")
            cause = f"Падение активности: {v}" if v is not None else "Падение активности"
            why_kv = {"metric": "activity_steps", "farm_id": farm_id, "when": str(when), **details}
            dk = f"SENSOR.ACTIVITY_DROP|animal|{animal_id}"
        elif a_type == "baseline_drift":
            alert_type = "SENSOR.BASELINE_DRIFT" if "SENSOR.BASELINE_DRIFT" in cat else "SENSOR.ANOMALY"
            cause = f"Дрейф baseline по {metric}"
            why_kv = {"metric": metric, "farm_id": farm_id, "when": str(when), **details}
            dk = f"{alert_type}|animal|{animal_id}|{metric}"
        else:
            # generic
            alert_type = "SENSOR.ANOMALY"
            cause = f"Аномалия сенсора: {a_type} ({metric})"
            why_kv = {"metric": metric, "farm_id": farm_id, "when": str(when), **details}
            dk = f"SENSOR.ANOMALY|animal|{animal_id}|{metric}|{a_type}"

        attachments = [
            {
                "kind": "cow_day",
                "dataset": "cow_day",
                "data_version": data_version,
                "animal_id": animal_id,
                "metric": why_kv.get("metric"),
                "date": str(when),
            }
        ]
        out.append(
            _mk_candidate(
                cat,
                alert_type=alert_type,
                object_type="animal",
                object_id=animal_id,
                cause=str(cause),
                confidence=None,
                attachments=attachments,
                why_kv=why_kv,
                data_version=data_version,
                today=today,
                dedupe_key=dk,
            )
        )

    return out


def generate_alerts_v2(
    *,
    artifacts_root: Path,
    data_version: str,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Aggregate generator: QC2 + ML risks + business rules.

    NOTE: Repro and sensor anomaly rules are catalogued, but generators are best-effort and will return
    empty list if corresponding datasets are missing.
    """
    today = today or date.today()
    canonical_dir = (artifacts_root / "canonical" / data_version) if (artifacts_root / "canonical" / data_version).exists() else (artifacts_root / data_version / "canonical")
    out: List[Dict[str, Any]] = []
    out.extend(generate_from_qc2(artifacts_root=artifacts_root, data_version=data_version, today=today))
    out.extend(generate_from_pedigree_qc(artifacts_root=artifacts_root, data_version=data_version, today=today))
    out.extend(generate_from_dm_alerts(canonical_dir=canonical_dir, data_version=data_version, today=today))
    out.extend(generate_mastitis_risk_alerts(artifacts_root=artifacts_root, data_version=data_version, today=today))
    out.extend(generate_withdrawal_alerts(canonical_dir=canonical_dir, data_version=data_version, today=today))
    out.extend(generate_repro_alerts(canonical_dir=canonical_dir, data_version=data_version, today=today))
    out.extend(generate_sensor_anomaly_alerts(canonical_dir=canonical_dir, data_version=data_version, today=today))
    # sensors daily rule-based detector (T3-03); best-effort when marts exist.
    out.extend(generate_sensor_daily_rule_alerts(artifacts_root=artifacts_root, data_version=data_version, today=today))
    return out
