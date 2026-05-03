from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from core.security import map_legacy_role
from genomeai.drilldown import compute_pen_assignments


LIST_OBJECT_TYPES: tuple[str, ...] = ("animals", "groups", "events")
SORT_DIRECTIONS: tuple[str, ...] = ("asc", "desc")


DEFAULT_COLUMNS: dict[str, tuple[str, ...]] = {
    "animals": (
        "animal_id",
        "status",
        "breed",
        "parity",
        "pen_name",
        "latest_event_date",
        "active_treatments",
        "latest_scc_cells_ml",
        "milk_quality_flag",
    ),
    "groups": (
        "pen_id",
        "pen_name",
        "pen_type",
        "site_id",
        "headcount",
        "capacity_head",
        "utilization_pct",
    ),
    "events": (
        "event_date",
        "event_family",
        "event_type",
        "animal_id",
        "pen_name",
        "status",
        "severity",
    ),
}


ROLE_VISIBLE_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "viewer": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "withdrawal_until", "source_table",
        ),
    },
    "director": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "withdrawal_until", "source_table",
        ),
    },
    "operator": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "treatment_type", "withdrawal_until",
            "source_table",
        ),
    },
    "zootech": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "treatment_type", "withdrawal_until",
            "notes", "source_table",
        ),
    },
    "vet": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "treatment_type", "withdrawal_until",
            "notes", "source_table",
        ),
    },
    "admin": {
        "animals": (
            "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex",
            "birth_date", "parity", "latest_event_date", "recent_health_events", "recent_repro_events",
            "active_treatments", "latest_scc_cells_ml", "milk_quality_flag",
        ),
        "groups": (
            "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
            "animals_with_health_events_30d", "utilization_pct",
        ),
        "events": (
            "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id",
            "pen_name", "event_type", "severity", "status", "result", "treatment_type", "withdrawal_until",
            "notes", "source_table",
        ),
    },
}

FILTER_FIELDS: dict[str, tuple[str, ...]] = {
    "animals": ("q", "farm_id", "site_id", "pen_id", "status", "sex", "breed", "animal_id"),
    "groups": ("q", "site_id", "pen_id", "pen_type"),
    "events": ("q", "farm_id", "site_id", "pen_id", "animal_id", "event_family", "event_type", "severity", "status", "date_from", "date_to"),
}


@dataclass(frozen=True)
class UniversalListSnapshot:
    object_type: str
    role: str
    rows: list[dict[str, Any]]
    total_before_limit: int
    returned_rows: int
    available_columns: tuple[str, ...]
    visible_columns: tuple[str, ...]
    selected_columns: tuple[str, ...]
    sort_by: str
    sort_dir: str
    filters: dict[str, Any]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def _parse_ts(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return pd.NaT
        return ts
    except Exception:
        return pd.NaT


def _normalize_object_type(value: str | None) -> str:
    key = str(value or "animals").strip().lower()
    if key in {"animal", "animals"}:
        return "animals"
    if key in {"group", "groups", "pen", "pens"}:
        return "groups"
    if key in {"event", "events"}:
        return "events"
    return "animals"


def _role_key(role: str | None) -> str:
    return map_legacy_role(str(role or "Viewer")).strip().lower() or "viewer"


def allowed_columns_for_role(*, object_type: str, role: str) -> tuple[str, ...]:
    key = _normalize_object_type(object_type)
    role_cfg = ROLE_VISIBLE_COLUMNS.get(_role_key(role)) or ROLE_VISIBLE_COLUMNS["viewer"]
    cols = tuple(str(x) for x in (role_cfg.get(key) or ROLE_VISIBLE_COLUMNS["viewer"][key]))
    return cols


def default_selected_columns(*, object_type: str, role: str) -> tuple[str, ...]:
    allowed = set(allowed_columns_for_role(object_type=object_type, role=role))
    preferred = DEFAULT_COLUMNS.get(_normalize_object_type(object_type), ())
    selected = tuple(col for col in preferred if col in allowed)
    return selected or tuple(sorted(allowed))


def _join_pen_assignments(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    try:
        assn = compute_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    except Exception:
        assn = pd.DataFrame()
    if assn is None or assn.empty:
        return pd.DataFrame(columns=["tenant_id", "animal_id", "farm_id", "site_id", "pen_id", "pen_name"])
    return assn.copy()


def _build_animals_df(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    animals = _read_csv(input_dir / "dm_animals.csv")
    if animals.empty:
        return pd.DataFrame(columns=["animal_id"])
    assn = _join_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    if not assn.empty:
        animals = animals.drop(columns=[c for c in ("current_pen_id", "current_pen_name", "pen_id", "pen_name") if c in animals.columns], errors="ignore")
        animals = animals.merge(
            assn[["animal_id", "farm_id", "site_id", "pen_id", "pen_name"]].drop_duplicates("animal_id"),
            on="animal_id",
            how="left",
            suffixes=("", "_assn"),
        )
    else:
        animals["pen_id"] = animals.get("current_pen_id")
        animals["pen_name"] = animals.get("current_pen_name")

    lact = _read_csv(input_dir / "dm_lactations.csv")
    if not lact.empty and "animal_id" in lact.columns:
        lact["calving_ts"] = pd.to_datetime(lact.get("calving_date"), errors="coerce")
        latest_lact = lact.sort_values(["animal_id", "calving_ts"], ascending=[True, False]).groupby("animal_id", as_index=False).head(1)
        latest_lact = latest_lact[[c for c in ("animal_id", "parity", "lactation_id", "calving_date") if c in latest_lact.columns]]
        animals = animals.merge(latest_lact, on="animal_id", how="left")

    health = _read_csv(input_dir / "dm_health_events.csv")
    repro = _read_csv(input_dir / "dm_repro_events.csv")
    treatments = _read_csv(input_dir / "dm_treatments.csv")

    if not health.empty and "animal_id" in health.columns:
        h = health.copy()
        h["event_ts"] = pd.to_datetime(h.get("event_date"), errors="coerce")
        h_agg = h.groupby("animal_id", dropna=False).agg(
            recent_health_events=("event_date", "count"),
            latest_health_event_date=("event_ts", "max"),
        ).reset_index()
        animals = animals.merge(h_agg, on="animal_id", how="left")
    else:
        animals["recent_health_events"] = 0
        animals["latest_health_event_date"] = pd.NaT

    if not repro.empty and "animal_id" in repro.columns:
        r = repro.copy()
        r["event_ts"] = pd.to_datetime(r.get("event_date"), errors="coerce")
        r_agg = r.groupby("animal_id", dropna=False).agg(
            recent_repro_events=("event_date", "count"),
            latest_repro_event_date=("event_ts", "max"),
        ).reset_index()
        animals = animals.merge(r_agg, on="animal_id", how="left")
    else:
        animals["recent_repro_events"] = 0
        animals["latest_repro_event_date"] = pd.NaT

    if not treatments.empty and "animal_id" in treatments.columns:
        t = treatments.copy()
        t["start_ts"] = pd.to_datetime(t.get("start_date"), errors="coerce")
        t["end_ts"] = pd.to_datetime(t.get("end_date"), errors="coerce")
        t["active_asof"] = t["end_ts"].isna() | (t["end_ts"].dt.date >= asof_date)
        t_agg = t.groupby("animal_id", dropna=False).agg(
            active_treatments=("active_asof", "sum"),
            latest_treatment_date=("start_ts", "max"),
        ).reset_index()
        animals = animals.merge(t_agg, on="animal_id", how="left")
    else:
        animals["active_treatments"] = 0
        animals["latest_treatment_date"] = pd.NaT

    latest_scc = pd.DataFrame(columns=["animal_id", "latest_scc_cells_ml"])
    testday = _read_csv(input_dir / "dm_testday.csv")
    if not testday.empty and "animal_id" in testday.columns and "scc_cells_ml" in testday.columns:
        td = testday.copy()
        td["record_ts"] = pd.to_datetime(td.get("test_date"), errors="coerce")
        latest_scc = td.sort_values(["animal_id", "record_ts"], ascending=[True, False]).groupby("animal_id", as_index=False).head(1)[["animal_id", "scc_cells_ml"]].rename(columns={"scc_cells_ml": "latest_scc_cells_ml"})
    elif not lact.empty and "animal_id" in lact.columns and "scc_cells_ml" in lact.columns:
        ll = lact.copy()
        ll["record_ts"] = pd.to_datetime(ll.get("calving_date"), errors="coerce")
        latest_scc = ll.sort_values(["animal_id", "record_ts"], ascending=[True, False]).groupby("animal_id", as_index=False).head(1)[["animal_id", "scc_cells_ml"]].rename(columns={"scc_cells_ml": "latest_scc_cells_ml"})
    if not latest_scc.empty:
        animals = animals.merge(latest_scc, on="animal_id", how="left")
    else:
        animals["latest_scc_cells_ml"] = pd.NA
    scc = pd.to_numeric(animals.get("latest_scc_cells_ml"), errors="coerce")
    animals["milk_quality_flag"] = "ok"
    animals.loc[pd.to_numeric(animals.get("active_treatments"), errors="coerce").fillna(0) > 0, "milk_quality_flag"] = "treatment_withdrawal"
    animals.loc[scc >= 200000, "milk_quality_flag"] = "high_scc"

    animals["latest_event_date"] = pd.to_datetime(
        pd.concat(
            [
                animals.get("latest_health_event_date", pd.Series(dtype="datetime64[ns]")),
                animals.get("latest_repro_event_date", pd.Series(dtype="datetime64[ns]")),
                animals.get("latest_treatment_date", pd.Series(dtype="datetime64[ns]")),
            ],
            axis=1,
        ).max(axis=1),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    animals["recent_health_events"] = pd.to_numeric(animals.get("recent_health_events"), errors="coerce").fillna(0).astype(int)
    animals["recent_repro_events"] = pd.to_numeric(animals.get("recent_repro_events"), errors="coerce").fillna(0).astype(int)
    animals["active_treatments"] = pd.to_numeric(animals.get("active_treatments"), errors="coerce").fillna(0).astype(int)
    animals["object_type"] = "animal"
    animals["object_id"] = animals.get("animal_id", pd.Series(dtype=object)).astype(str)
    animals["open_target"] = "animal"

    preferred = [
        "animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex", "birth_date",
        "parity", "lactation_id", "calving_date", "recent_health_events", "recent_repro_events",
        "active_treatments", "latest_scc_cells_ml", "milk_quality_flag", "latest_event_date", "object_type", "object_id", "open_target",
    ]
    for col in preferred:
        if col not in animals.columns:
            animals[col] = pd.NA
    return animals[preferred].copy()


def _build_groups_df(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    pens = _read_csv(input_dir / "dm_pens.csv")
    if pens.empty:
        return pd.DataFrame(columns=["pen_id"])

    pens = pens.copy()
    if "pen_type" not in pens.columns and "group_type" in pens.columns:
        pens["pen_type"] = pens["group_type"]
    assn = _join_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    animals = _read_csv(input_dir / "dm_animals.csv")
    health = _read_csv(input_dir / "dm_health_events.csv")

    if not assn.empty:
        headcount = assn.groupby("pen_id", dropna=False).agg(headcount=("animal_id", "nunique")).reset_index()
        pens = pens.merge(headcount, on="pen_id", how="left")
        if not animals.empty:
            merged = assn[["animal_id", "pen_id"]].merge(animals[[c for c in ("animal_id", "status") if c in animals.columns]], on="animal_id", how="left")
            active = merged[merged.get("status", pd.Series(dtype=object)).astype(str).str.lower().isin(["active", "milking", "open", "pregnant"])].groupby("pen_id", dropna=False).agg(active_animals=("animal_id", "nunique")).reset_index()
            pens = pens.merge(active, on="pen_id", how="left")
        if not health.empty and "animal_id" in health.columns:
            recent_animals = set(health[health.get("event_date", pd.Series(dtype=object)).astype(str) >= (pd.Timestamp(asof_date) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")].get("animal_id", pd.Series(dtype=object)).astype(str).tolist())
            flagged = assn[assn.get("animal_id", pd.Series(dtype=object)).astype(str).isin(recent_animals)].groupby("pen_id", dropna=False).agg(animals_with_health_events_30d=("animal_id", "nunique")).reset_index()
            pens = pens.merge(flagged, on="pen_id", how="left")
    pens["headcount"] = pd.to_numeric(pens.get("headcount"), errors="coerce").fillna(0).astype(int)
    pens["active_animals"] = pd.to_numeric(pens.get("active_animals"), errors="coerce").fillna(0).astype(int)
    pens["animals_with_health_events_30d"] = pd.to_numeric(pens.get("animals_with_health_events_30d"), errors="coerce").fillna(0).astype(int)
    cap = pd.to_numeric(pens.get("capacity_head"), errors="coerce")
    pens["utilization_pct"] = ((pens["headcount"] / cap.replace({0: pd.NA})) * 100.0).round(1)
    pens["object_type"] = "group"
    pens["object_id"] = pens.get("pen_id", pd.Series(dtype=object)).astype(str)
    pens["open_target"] = "group"
    preferred = [
        "pen_id", "pen_name", "site_id", "pen_type", "capacity_head", "headcount", "active_animals",
        "animals_with_health_events_30d", "utilization_pct", "object_type", "object_id", "open_target",
    ]
    for col in preferred:
        if col not in pens.columns:
            pens[col] = pd.NA
    return pens[preferred].copy()


def _build_events_df(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    animals = _read_csv(input_dir / "dm_animals.csv")
    assn = _join_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    animal_ctx = pd.DataFrame(columns=["animal_id", "farm_id", "site_id", "pen_id", "pen_name"])
    if not animals.empty:
        animal_ctx = animals[[c for c in ("animal_id", "farm_id", "site_id") if c in animals.columns]].copy()
        if not assn.empty:
            animal_ctx = animal_ctx.merge(assn[["animal_id", "pen_id", "pen_name"]].drop_duplicates("animal_id"), on="animal_id", how="left")
        else:
            animal_ctx["pen_id"] = animals.get("current_pen_id")
            animal_ctx["pen_name"] = animals.get("current_pen_name")

    frames: list[pd.DataFrame] = []

    health = _read_csv(input_dir / "dm_health_events.csv")
    if not health.empty:
        df = health.copy()
        if "event_id" not in df.columns:
            df["event_id"] = df.index.astype(str)
        df["event_family"] = "health"
        df["status"] = "recorded"
        df["source_table"] = "dm_health_events"
        frames.append(df.rename(columns={"event_date": "event_date", "event_type": "event_type"}))

    repro = _read_csv(input_dir / "dm_repro_events.csv")
    if not repro.empty:
        df = repro.copy()
        if "event_id" not in df.columns:
            df["event_id"] = df.get("repro_event_id", df.index.astype(str))
        df["event_family"] = "reproduction"
        df["status"] = df.get("result", pd.Series(dtype=object)).fillna("recorded")
        df["severity"] = pd.NA
        df["source_table"] = "dm_repro_events"
        frames.append(df.rename(columns={"event_date": "event_date", "event_type": "event_type"}))

    treatments = _read_csv(input_dir / "dm_treatments.csv")
    if not treatments.empty:
        df = treatments.copy()
        if "event_id" not in df.columns:
            df["event_id"] = df.get("treatment_id", df.index.astype(str))
        df["event_family"] = "treatment"
        df["event_date"] = df.get("start_date")
        df["event_type"] = df.get("treatment_type")
        df["treatment_type"] = df.get("treatment_type")
        end_ts = pd.to_datetime(df.get("end_date"), errors="coerce")
        start_ts = pd.to_datetime(df.get("start_date"), errors="coerce")
        df["status"] = "active"
        df.loc[start_ts.dt.date > asof_date, "status"] = "planned"
        df.loc[end_ts.notna() & (end_ts.dt.date < asof_date), "status"] = "completed"
        df["severity"] = pd.NA
        df["notes"] = df.get("reason_event_id")
        df["withdrawal_until"] = df.get("withdrawal_end_date")
        df["source_table"] = "dm_treatments"
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["event_id"])

    events = pd.concat(frames, axis=0, ignore_index=True, sort=False)
    if not animal_ctx.empty and "animal_id" in events.columns:
        events = events.merge(animal_ctx.drop_duplicates("animal_id"), on="animal_id", how="left")

    preferred = [
        "event_id", "event_family", "event_date", "animal_id", "farm_id", "site_id", "pen_id", "pen_name",
        "event_type", "severity", "status", "result", "treatment_type", "withdrawal_until", "notes",
        "source_table",
    ]
    for col in preferred:
        if col not in events.columns:
            events[col] = pd.NA
    events["object_type"] = "animal"
    events["object_id"] = events.get("animal_id", pd.Series(dtype=object)).astype(str)
    events["open_target"] = "animal"
    events["event_date_ts"] = pd.to_datetime(events.get("event_date"), errors="coerce")
    return events[preferred + ["object_type", "object_id", "open_target", "event_date_ts"]].copy()


def _contains_series(df: pd.DataFrame, columns: Iterable[str], query: str) -> pd.Series:
    q = str(query or "").strip().lower()
    if not q or df.empty:
        return pd.Series([True] * len(df), index=df.index)
    acc = pd.Series([False] * len(df), index=df.index)
    for col in columns:
        if col not in df.columns:
            continue
        acc = acc | df[col].astype(str).str.lower().str.contains(q, na=False)
    return acc


def _apply_common_filters(df: pd.DataFrame, *, object_type: str, filters: Mapping[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    key = _normalize_object_type(object_type)
    for name in FILTER_FIELDS.get(key, ()):
        raw = filters.get(name)
        if raw in (None, "", []):
            continue
        if name == "q":
            qcols = {
                "animals": ("animal_id", "breed", "status", "pen_name", "pen_id"),
                "groups": ("pen_id", "pen_name", "pen_type", "site_id"),
                "events": ("event_id", "event_family", "event_type", "animal_id", "pen_name", "notes", "status"),
            }.get(key, ())
            out = out[_contains_series(out, qcols, str(raw))]
            continue
        if name == "date_from" and "event_date_ts" in out.columns:
            dt = _parse_ts(raw)
            if pd.notna(dt):
                out = out[out["event_date_ts"] >= dt.normalize()]
            continue
        if name == "date_to" and "event_date_ts" in out.columns:
            dt = _parse_ts(raw)
            if pd.notna(dt):
                out = out[out["event_date_ts"] <= dt.normalize()]
            continue
        if name in out.columns:
            out = out[out[name].astype(str).str.lower() == str(raw).strip().lower()]
    return out


def _apply_sort(df: pd.DataFrame, *, sort_by: str | None, sort_dir: str | None) -> tuple[pd.DataFrame, str, str]:
    if df.empty:
        return df.copy(), _clean(sort_by) or "", (str(sort_dir or "asc").lower() if str(sort_dir or "asc").lower() in SORT_DIRECTIONS else "asc")
    chosen = _clean(sort_by)
    if chosen not in df.columns:
        preferred = next((c for c in ("event_date_ts", "latest_event_date", "animal_id", "pen_name", "event_id", "pen_id") if c in df.columns), df.columns[0])
        chosen = str(preferred)
    direction = str(sort_dir or "asc").strip().lower()
    if direction not in SORT_DIRECTIONS:
        direction = "asc"
    asc = direction == "asc"
    try:
        return df.sort_values(by=[chosen], ascending=asc, na_position="last"), chosen, direction
    except Exception:
        return df.copy(), chosen, direction


def build_universal_list_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    role: str,
    object_type: str,
    filters: Mapping[str, Any] | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    selected_columns: Sequence[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    base = Path(input_dir)
    otype = _normalize_object_type(object_type)
    role_norm = _role_key(role)
    if otype == "animals":
        df = _build_animals_df(input_dir=base, asof_date=asof_date)
    elif otype == "groups":
        df = _build_groups_df(input_dir=base, asof_date=asof_date)
    else:
        df = _build_events_df(input_dir=base, asof_date=asof_date)

    flt = {str(k): v for k, v in dict(filters or {}).items()}
    df = _apply_common_filters(df, object_type=otype, filters=flt)
    total_before_limit = int(len(df))
    df, sort_used, dir_used = _apply_sort(df, sort_by=sort_by, sort_dir=sort_dir)
    df = df.head(max(1, int(limit))) if int(limit or 0) > 0 else df

    visible = tuple(col for col in allowed_columns_for_role(object_type=otype, role=role_norm) if col in df.columns)
    selected = tuple(col for col in (selected_columns or default_selected_columns(object_type=otype, role=role_norm)) if col in visible)
    if not selected:
        selected = default_selected_columns(object_type=otype, role=role_norm)
        selected = tuple(col for col in selected if col in visible)

    records = df.to_dict(orient="records") if not df.empty else []
    return {
        "object_type": otype,
        "role": role_norm,
        "rows": records,
        "total_before_limit": total_before_limit,
        "returned_rows": len(records),
        "available_columns": tuple(str(c) for c in df.columns if c not in {"event_date_ts", "object_type", "object_id", "open_target"}),
        "visible_columns": visible,
        "selected_columns": selected,
        "sort_by": sort_used,
        "sort_dir": dir_used,
        "filters": flt,
    }


def build_universal_list_table(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    rows = list(snapshot.get("rows") or [])
    selected = [str(c) for c in (snapshot.get("selected_columns") or []) if str(c).strip()]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=selected)
    cols = [c for c in selected if c in df.columns]
    return df[cols].copy() if cols else df.copy()


def export_universal_list(snapshot: Mapping[str, Any], *, fmt: str) -> bytes:
    df = build_universal_list_table(snapshot)
    kind = str(fmt or "csv").strip().lower()
    if kind == "xlsx":
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="list", index=False)
        return buf.getvalue()
    return df.to_csv(index=False).encode("utf-8")


__all__ = [
    "DEFAULT_COLUMNS",
    "FILTER_FIELDS",
    "LIST_OBJECT_TYPES",
    "ROLE_VISIBLE_COLUMNS",
    "SORT_DIRECTIONS",
    "allowed_columns_for_role",
    "build_universal_list_snapshot",
    "build_universal_list_table",
    "default_selected_columns",
    "export_universal_list",
]
