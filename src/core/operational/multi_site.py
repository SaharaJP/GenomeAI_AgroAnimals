from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from genomeai.drilldown import compute_pen_assignments


_SCOPE_COLS = [
    "farm_id",
    "farm_name",
    "site_id",
    "site_name",
    "group_id",
    "group_name",
    "pen_id",
    "pen_name",
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = _clean(value)
        if text and text not in out:
            out.append(text)
    return out


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def _coalesce(*values: Any) -> str:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return ""


def _scope_label(prefix: str, ident: str, name: str) -> str:
    ident_v = _clean(ident)
    name_v = _clean(name)
    if ident_v and name_v and name_v != ident_v:
        return f"{prefix} {name_v} ({ident_v})"
    if name_v:
        return f"{prefix} {name_v}"
    if ident_v:
        return f"{prefix} {ident_v}"
    return ""


def _build_path(parts: Sequence[str]) -> str:
    clean_parts = [p for p in (_clean(x) for x in parts) if p]
    return " → ".join(clean_parts)


def build_multi_site_reference(*, input_dir: Path) -> pd.DataFrame:
    """Build enterprise-ready farm/site/group/pen reference.

    Compatibility rule:
    - if no explicit group_id/group_name exists, group falls back to pen.
    - existing farm/site/pen abstractions stay intact.
    """
    farms = _read_csv(Path(input_dir) / "dm_farms.csv")
    sites = _read_csv(Path(input_dir) / "dm_sites.csv")
    pens = _read_csv(Path(input_dir) / "dm_pens.csv")

    if farms.empty:
        farms = pd.DataFrame(columns=["tenant_id", "farm_id", "farm_name"])
    if sites.empty:
        sites = pd.DataFrame(columns=["tenant_id", "site_id", "farm_id", "site_name"])
    if pens.empty:
        pens = pd.DataFrame(columns=["tenant_id", "pen_id", "site_id", "pen_name", "pen_type", "group_id", "group_name"])

    for col in ["tenant_id", "farm_id", "farm_name"]:
        if col not in farms.columns:
            farms[col] = pd.NA
    for col in ["tenant_id", "site_id", "farm_id", "site_name"]:
        if col not in sites.columns:
            sites[col] = pd.NA
    for col in ["tenant_id", "pen_id", "site_id", "pen_name", "pen_type", "group_id", "group_name"]:
        if col not in pens.columns:
            pens[col] = pd.NA

    out = pens[["tenant_id", "pen_id", "site_id", "pen_name", "pen_type", "group_id", "group_name"]].copy()
    out = out.merge(sites[["tenant_id", "site_id", "farm_id", "site_name"]], on=["tenant_id", "site_id"], how="left")
    out = out.merge(farms[["tenant_id", "farm_id", "farm_name"]], on=["tenant_id", "farm_id"], how="left")

    for col in ["tenant_id", "farm_id", "farm_name", "site_id", "site_name", "pen_id", "pen_name", "pen_type", "group_id", "group_name"]:
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = out[col].astype("string")

    out["group_id"] = out["group_id"].fillna(out["pen_id"])
    out["group_name"] = out["group_name"].fillna(out["pen_name"])

    out["farm_label"] = [
        _scope_label("Farm", row.get("farm_id"), row.get("farm_name"))
        for _, row in out.iterrows()
    ]
    out["site_label"] = [
        _scope_label("Site", row.get("site_id"), row.get("site_name"))
        for _, row in out.iterrows()
    ]
    out["group_label"] = [
        _scope_label("Group", row.get("group_id"), row.get("group_name"))
        for _, row in out.iterrows()
    ]
    out["pen_label"] = [
        _scope_label("Pen", row.get("pen_id"), row.get("pen_name"))
        for _, row in out.iterrows()
    ]
    out["physical_location"] = [
        _build_path([row.get("farm_label"), row.get("site_label"), row.get("pen_label")])
        for _, row in out.iterrows()
    ]
    out["organizational_location"] = [
        _build_path([row.get("farm_label"), row.get("site_label"), row.get("group_label")])
        for _, row in out.iterrows()
    ]
    out["lineage_path"] = [
        _build_path([
            f"farm:{_clean(row.get('farm_id'))}" if _clean(row.get("farm_id")) else "",
            f"site:{_clean(row.get('site_id'))}" if _clean(row.get("site_id")) else "",
            f"group:{_clean(row.get('group_id'))}" if _clean(row.get("group_id")) else "",
            f"pen:{_clean(row.get('pen_id'))}" if _clean(row.get("pen_id")) else "",
        ])
        for _, row in out.iterrows()
    ]

    keep = [
        "tenant_id", "farm_id", "farm_name", "site_id", "site_name", "group_id", "group_name",
        "pen_id", "pen_name", "pen_type", "farm_label", "site_label", "group_label", "pen_label",
        "physical_location", "organizational_location", "lineage_path",
    ]
    out = out[keep].drop_duplicates().reset_index(drop=True)
    return out


def build_current_location_index(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    assn = compute_pen_assignments(input_dir=Path(input_dir), asof_date=asof_date)
    ref = build_multi_site_reference(input_dir=Path(input_dir))

    if assn.empty:
        cols = ["tenant_id", "animal_id"] + _SCOPE_COLS + ["physical_location", "organizational_location", "lineage_path"]
        return pd.DataFrame(columns=cols)

    for col in ["tenant_id", "animal_id", "farm_id", "site_id", "pen_id", "pen_name"]:
        if col not in assn.columns:
            assn[col] = pd.NA
    out = assn.copy()
    out = out.merge(
        ref[[
            "tenant_id", "pen_id", "farm_id", "farm_name", "site_id", "site_name", "group_id", "group_name",
            "pen_name", "physical_location", "organizational_location", "lineage_path",
        ]].rename(columns={"farm_id": "farm_id_ref", "site_id": "site_id_ref", "pen_name": "pen_name_ref"}),
        on=["tenant_id", "pen_id"],
        how="left",
    )
    out["farm_id"] = out["farm_id"].fillna(out["farm_id_ref"])
    out["site_id"] = out["site_id"].fillna(out["site_id_ref"])
    out["pen_name"] = out["pen_name"].fillna(out["pen_name_ref"])
    out.drop(columns=[c for c in ["farm_id_ref", "site_id_ref", "pen_name_ref"] if c in out.columns], inplace=True)
    for col in _SCOPE_COLS + ["physical_location", "organizational_location", "lineage_path"]:
        if col not in out.columns:
            out[col] = pd.NA
    return out[["tenant_id", "animal_id"] + _SCOPE_COLS + ["physical_location", "organizational_location", "lineage_path"]].copy()


def resolve_operational_location(
    *,
    current_index: pd.DataFrame,
    reference: pd.DataFrame,
    animal_id: str | None = None,
    pen_id: str | None = None,
    group_id: str | None = None,
    farm_id: str | None = None,
    site_id: str | None = None,
) -> dict[str, Any]:
    animal_key = _clean(animal_id)
    pen_key = _clean(pen_id)
    group_key = _clean(group_id)
    farm_key = _clean(farm_id)
    site_key = _clean(site_id)

    if animal_key and not current_index.empty:
        hit = current_index[current_index["animal_id"].astype(str) == animal_key].head(1)
        if not hit.empty:
            return hit.iloc[0].to_dict()

    ref = reference.copy() if reference is not None else pd.DataFrame()
    if not ref.empty:
        if pen_key and "pen_id" in ref.columns:
            hit = ref[ref["pen_id"].astype(str) == pen_key].head(1)
            if not hit.empty:
                return hit.iloc[0].to_dict()
        if group_key and "group_id" in ref.columns:
            hit = ref[ref["group_id"].astype(str) == group_key].head(1)
            if not hit.empty:
                return hit.iloc[0].to_dict()
        if site_key and "site_id" in ref.columns:
            hit = ref[ref["site_id"].astype(str) == site_key].head(1)
            if not hit.empty:
                return hit.iloc[0].to_dict()
        if farm_key and "farm_id" in ref.columns:
            hit = ref[ref["farm_id"].astype(str) == farm_key].head(1)
            if not hit.empty:
                return hit.iloc[0].to_dict()

    return {
        "farm_id": farm_key or None,
        "site_id": site_key or None,
        "group_id": group_key or pen_key or None,
        "pen_id": pen_key or group_key or None,
        "farm_name": None,
        "site_name": None,
        "group_name": None,
        "pen_name": None,
        "physical_location": "",
        "organizational_location": "",
        "lineage_path": _build_path([
            f"farm:{farm_key}" if farm_key else "",
            f"site:{site_key}" if site_key else "",
            f"group:{group_key or pen_key}" if (group_key or pen_key) else "",
            f"pen:{pen_key or group_key}" if (pen_key or group_key) else "",
        ]),
    }


def enrich_operational_items(*, rows: Sequence[Mapping[str, Any]], input_dir: Path, asof_date: date) -> list[dict[str, Any]]:
    current_index = build_current_location_index(input_dir=Path(input_dir), asof_date=asof_date)
    reference = build_multi_site_reference(input_dir=Path(input_dir))
    enriched: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        why = dict(row.get("why") or {}) if isinstance(row.get("why"), Mapping) else {}
        source_chain = dict(row.get("source_chain") or {}) if isinstance(row.get("source_chain"), Mapping) else {}
        object_type = _clean(row.get("object_type"))
        object_id = _clean(row.get("object_id"))

        explicit_pen = _coalesce(row.get("pen_id"), row.get("group_id"), why.get("pen_id"), why.get("group_id"))
        explicit_group = _coalesce(row.get("group_id"), why.get("group_id"), explicit_pen)
        explicit_site = _coalesce(row.get("site_id"), why.get("site_id"))
        explicit_farm = _coalesce(row.get("farm_id"), why.get("farm_id"))

        if object_type == "animal" and object_id:
            loc = resolve_operational_location(current_index=current_index, reference=reference, animal_id=object_id)
        elif object_type in {"group", "pen"} and object_id:
            loc = resolve_operational_location(current_index=current_index, reference=reference, pen_id=object_id, group_id=object_id)
        else:
            loc = resolve_operational_location(
                current_index=current_index,
                reference=reference,
                pen_id=explicit_pen or None,
                group_id=explicit_group or None,
                site_id=explicit_site or None,
                farm_id=explicit_farm or None,
            )

        row["farm_id"] = _coalesce(loc.get("farm_id"), explicit_farm) or None
        row["site_id"] = _coalesce(loc.get("site_id"), explicit_site) or None
        row["group_id"] = _coalesce(loc.get("group_id"), explicit_group, explicit_pen) or None
        row["pen_id"] = _coalesce(loc.get("pen_id"), explicit_pen, explicit_group) or None
        row["farm_name"] = _clean(loc.get("farm_name")) or None
        row["site_name"] = _clean(loc.get("site_name")) or None
        row["group_name"] = _coalesce(loc.get("group_name"), loc.get("pen_name")) or None
        row["pen_name"] = _clean(loc.get("pen_name")) or None
        row["physical_location"] = _clean(loc.get("physical_location")) or None
        row["organizational_location"] = _clean(loc.get("organizational_location")) or None
        row["lineage_path"] = _clean(loc.get("lineage_path")) or None
        row["scope_label"] = _build_path([
            _scope_label("Farm", row.get("farm_id"), row.get("farm_name")),
            _scope_label("Site", row.get("site_id"), row.get("site_name")),
            _scope_label("Group", row.get("group_id"), row.get("group_name")),
        ]) or _clean(row.get("organizational_location"))
        row["linked_lineage"] = {
            "farm_id": row.get("farm_id"),
            "site_id": row.get("site_id"),
            "group_id": row.get("group_id"),
            "pen_id": row.get("pen_id"),
            "lineage_path": row.get("lineage_path"),
            "physical_location": row.get("physical_location"),
            "organizational_location": row.get("organizational_location"),
            "source_chain_keys": sorted(source_chain.keys()),
        }
        enriched.append(row)
    return enriched


def filter_operational_items(
    rows: Sequence[Mapping[str, Any]],
    *,
    farm_id: str | None = None,
    site_id: str | None = None,
    group_id: str | None = None,
    pen_id: str | None = None,
    allowed_farm_ids: Iterable[Any] | None = None,
    allowed_site_ids: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    farm_filter = _clean(farm_id)
    site_filter = _clean(site_id)
    group_filter = _clean(group_id)
    pen_filter = _clean(pen_id)
    allowed_farms = set(_clean_list(allowed_farm_ids))
    allowed_sites = set(_clean_list(allowed_site_ids))

    out: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        row_farm = _clean(row.get("farm_id"))
        row_site = _clean(row.get("site_id"))
        row_group = _clean(row.get("group_id"))
        row_pen = _clean(row.get("pen_id"))
        if allowed_farms and row_farm and row_farm not in allowed_farms:
            continue
        if allowed_sites and row_site and row_site not in allowed_sites:
            continue
        if farm_filter and row_farm != farm_filter:
            continue
        if site_filter and row_site != site_filter:
            continue
        if group_filter and row_group != group_filter:
            continue
        if pen_filter and row_pen != pen_filter:
            continue
        out.append(row)
    return out


def build_scope_options(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    df = pd.DataFrame(list(rows or []))
    if df.empty:
        return {"farm_ids": [], "site_ids": [], "group_ids": [], "pen_ids": []}
    out: dict[str, list[str]] = {}
    for key in ["farm_id", "site_id", "group_id", "pen_id"]:
        if key in df.columns:
            out[f"{key}s"] = sorted([x for x in df[key].astype(str).unique().tolist() if x not in {"", "nan", "None"}])
        else:
            out[f"{key}s"] = []
    return out


def build_explainable_scope_aggregates(rows: Sequence[Mapping[str, Any]], *, level: str) -> pd.DataFrame:
    level_key = str(level or "site").strip().lower()
    key_map = {
        "farm": ["farm_id", "farm_name"],
        "site": ["farm_id", "farm_name", "site_id", "site_name"],
        "group": ["farm_id", "farm_name", "site_id", "site_name", "group_id", "group_name"],
        "pen": ["farm_id", "farm_name", "site_id", "site_name", "pen_id", "pen_name"],
    }
    group_cols = key_map.get(level_key, key_map["site"])
    df = pd.DataFrame(list(rows or []))
    if df.empty:
        extra_cols = ["items_total", "high_priority", "overdue", "today", "animals_n", "source_kinds", "object_types", "explainability"]
        return pd.DataFrame(columns=group_cols + extra_cols)

    for col in group_cols + ["priority", "bucket", "object_type", "object_id", "source_kind"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["priority_num"] = pd.to_numeric(df["priority"], errors="coerce").fillna(3)
    rows_out: list[dict[str, Any]] = []
    for keys, sub in df.groupby(group_cols, dropna=False, sort=True):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        record = {col: (None if pd.isna(val) else val) for col, val in zip(group_cols, key_values)}
        record["items_total"] = int(len(sub))
        record["high_priority"] = int((sub["priority_num"] <= 2).sum())
        record["overdue"] = int((sub["bucket"].astype(str) == "overdue").sum())
        record["today"] = int((sub["bucket"].astype(str) == "today").sum())
        animal_ids = [x for x in sub.loc[sub["object_type"].astype(str) == "animal", "object_id"].astype(str).tolist() if x and x not in {"nan", "None"}]
        record["animals_n"] = len(sorted(set(animal_ids)))
        source_kinds = sorted({str(x) for x in sub["source_kind"].astype(str).tolist() if str(x).strip() and str(x) not in {"nan", "None"}})
        object_types = sorted({str(x) for x in sub["object_type"].astype(str).tolist() if str(x).strip() and str(x) not in {"nan", "None"}})
        record["source_kinds"] = ", ".join(source_kinds) or "—"
        record["object_types"] = ", ".join(object_types) or "—"
        record["explainability"] = f"{int(len(sub))} items = {', '.join(source_kinds) or 'unknown sources'}"
        rows_out.append(record)
    return pd.DataFrame(rows_out)


def format_operational_location(*, row: Mapping[str, Any] | None) -> dict[str, str]:
    row = dict(row or {})
    farm_label = _scope_label("Farm", row.get("farm_id"), row.get("farm_name"))
    site_label = _scope_label("Site", row.get("site_id"), row.get("site_name"))
    group_label = _scope_label("Group", row.get("group_id"), row.get("group_name") or row.get("pen_name"))
    pen_label = _scope_label("Pen", row.get("pen_id"), row.get("pen_name"))
    return {
        "farm_label": farm_label,
        "site_label": site_label,
        "group_label": group_label,
        "pen_label": pen_label,
        "physical_location": _build_path([farm_label, site_label, pen_label]),
        "organizational_location": _build_path([farm_label, site_label, group_label]),
        "lineage_path": _build_path([
            f"farm:{_clean(row.get('farm_id'))}" if _clean(row.get("farm_id")) else "",
            f"site:{_clean(row.get('site_id'))}" if _clean(row.get("site_id")) else "",
            f"group:{_clean(row.get('group_id') or row.get('pen_id'))}" if _clean(row.get("group_id") or row.get("pen_id")) else "",
            f"pen:{_clean(row.get('pen_id'))}" if _clean(row.get("pen_id")) else "",
        ]),
    }


__all__ = [
    "build_current_location_index",
    "build_explainable_scope_aggregates",
    "build_multi_site_reference",
    "build_scope_options",
    "enrich_operational_items",
    "filter_operational_items",
    "format_operational_location",
    "resolve_operational_location",
]
