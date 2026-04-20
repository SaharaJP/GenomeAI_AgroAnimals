from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from core.application.qc_reporting import build_issue_counts, build_row_counts, write_qc_output_bundle
from core.domain import AutoAlert, QC_SEVERITIES, QcIssue


@dataclass(frozen=True)
class QcConfigRef:
    path: str
    format: str
    config_version: str
    rules_sha256: str
    rules_count: int


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_qc_run_id() -> str:
    rnd = hashlib.sha256(str(time.time()).encode("utf-8")).hexdigest()[:6]
    return time.strftime(f"qc2_%Y%m%d_%H%M%S_{rnd}", time.gmtime())


SEVERITIES = set(QC_SEVERITIES)


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_rules_doc(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        obj = json.loads(raw)
    else:
        obj = yaml.safe_load(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"QC config must be an object: {path}")
    return obj


def load_qc_rules(path: Path) -> Dict[str, Any]:
    obj = _read_rules_doc(path)
    if "rules" not in obj:
        raise ValueError(f"QC config must contain 'rules': {path}")
    rules = obj.get("rules")
    if not isinstance(rules, list) or len(rules) < 1:
        raise ValueError(f"QC config 'rules' must be a non-empty list: {path}")

    seen: set[str] = set()
    for r in rules:
        if not isinstance(r, dict):
            raise ValueError("Each QC rule must be an object")
        rid = str(r.get("id"))
        if not rid or rid == "None":
            raise ValueError("QC rule is missing 'id'")
        if rid in seen:
            raise ValueError(f"Duplicate QC rule id: {rid}")
        seen.add(rid)
        sev = str(r.get("severity"))
        if sev not in SEVERITIES:
            raise ValueError(f"Rule {rid}: invalid severity {sev} (expected {sorted(SEVERITIES)})")
        if not str(r.get("remediation") or "").strip():
            raise ValueError(f"Rule {rid}: remediation must be non-empty")
    return obj


def load_qc_config_ref(path: Path) -> QcConfigRef:
    obj = load_qc_rules(path)
    sha = _sha256_file(path)
    version_raw = obj.get("config_version") or obj.get("version") or f"sha256:{sha[:12]}"
    config_version = str(version_raw)
    fmt = "json" if path.suffix.lower() == ".json" else "yaml"
    return QcConfigRef(
        path=str(path),
        format=fmt,
        config_version=config_version,
        rules_sha256=sha,
        rules_count=len(list(obj.get("rules") or [])),
    )


def _rule_alert_template(rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    a = rule.get("alert")
    if not a or not isinstance(a, dict):
        return None
    if not bool(a.get("create", False)):
        return None
    return a


def _new_alert_id(rule_id: str, suffix: str) -> str:
    h = hashlib.sha256(f"{rule_id}:{suffix}".encode("utf-8")).hexdigest()[:10]
    return f"al_{h}"


def _safe_read_table(canonical_dir: Path, dataset: str) -> Optional[pd.DataFrame]:
    pq = canonical_dir / f"{dataset}.parquet"
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    csv = canonical_dir / f"{dataset}.csv"
    if csv.exists():
        return pd.read_csv(csv)
    return None


def _as_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x)
    return None if s.strip() == "" else s


def _row_id(df: pd.DataFrame, idx: int, cols: Optional[List[str]] = None) -> str:
    if cols:
        vals: List[str] = []
        for c in cols:
            if c not in df.columns:
                continue
            vals.append(str(df.loc[idx, c]))
        if vals:
            return "|".join(vals)
    return f"row:{int(idx) + 2}"


def _to_date_series(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    return dt.dt.date


def evaluate_rule_based_qc(
    *,
    artifacts_root: Path,
    data_version: str,
    rules_path: Path,
    qc_run: str,
    tenant_id: str = "default",
    max_issue_rows_per_rule: int = 200,
) -> dict[str, Any]:
    artifacts_root = artifacts_root.resolve()
    base = artifacts_root / data_version
    canonical_dir = base / "canonical"
    if not canonical_dir.exists():
        raise FileNotFoundError(f"Canonical dir not found: {canonical_dir}")

    rules_doc = load_qc_rules(rules_path)
    cfg = load_qc_config_ref(rules_path)
    rules: List[Dict[str, Any]] = list(rules_doc.get("rules", []))

    dfs: Dict[str, pd.DataFrame] = {}
    datasets_loaded: dict[str, int] = {}

    def get_df(ds: str) -> Optional[pd.DataFrame]:
        if ds in dfs:
            return dfs[ds]
        df = _safe_read_table(canonical_dir, ds)
        if df is None:
            return None
        df.columns = [str(c).strip() for c in df.columns]
        dfs[ds] = df
        datasets_loaded[ds] = int(len(df))
        return df

    issues: List[QcIssue] = []
    alerts: List[AutoAlert] = []
    metrics: dict[str, int] = {"rules_total": int(len(rules))}
    today = date.today()

    def add_issue(*, rule: Dict[str, Any], msg: str, row_id: Optional[str] = None, field: Optional[str] = None, sample_value: Optional[str] = None) -> None:
        issues.append(
            QcIssue(
                qc_run=qc_run,
                data_version=data_version,
                rule_id=str(rule["id"]),
                domain=str(rule.get("domain", "general")),
                dataset=str(rule.get("dataset", "")),
                severity=str(rule.get("severity")),
                message=msg,
                remediation=str(rule.get("remediation")),
                row_id=row_id,
                field=field,
                sample_value=sample_value,
            )
        )

    def maybe_create_alert(rule: Dict[str, Any], *, farm_id: str, message: str, entity_type: Optional[str], entity_id: Optional[str]) -> None:
        a = _rule_alert_template(rule)
        if not a:
            return
        alert_type = str(a.get("alert_type") or "qc_issue")
        sev = str(a.get("severity") or rule.get("severity") or "MAJOR")
        suffix = f"{tenant_id}|{farm_id}|{entity_type}|{entity_id}|{alert_type}"
        alert_id = _new_alert_id(str(rule["id"]), suffix)
        alerts.append(
            AutoAlert(
                alert_id=alert_id,
                tenant_id=tenant_id,
                farm_id=farm_id,
                alert_date=str(today),
                severity=sev,
                alert_type=alert_type,
                entity_type=entity_type,
                entity_id=entity_id,
                message=message,
                source_rule_id=str(rule["id"]),
                qc_run=qc_run,
                data_version=data_version,
            )
        )

    def rule_limit() -> int:
        return int(max_issue_rows_per_rule)

    for rule in rules:
        ds = str(rule.get("dataset"))
        rtype = str(rule.get("type"))
        df = get_df(ds)
        if df is None:
            metrics[f"rule_skipped_missing_dataset:{rule['id']}"] = 1
            continue

        if rtype == "fk_exists":
            if rule.get("child_column") is None and rule.get("child_col") is not None:
                rule["child_column"] = rule.get("child_col")
            if rule.get("parent_column") is None and rule.get("parent_col") is not None:
                rule["parent_column"] = rule.get("parent_col")
            if rule.get("parent_dataset") is None and rule.get("parent_ds") is not None:
                rule["parent_dataset"] = rule.get("parent_ds")
        if rtype == "join_date_order":
            if rule.get("left_on") is None and rule.get("left_keys") is not None:
                rule["left_on"] = rule.get("left_keys")
            if rule.get("right_on") is None and rule.get("right_keys") is not None:
                rule["right_on"] = rule.get("right_keys")
            if rule.get("left_date") is None and rule.get("left") is not None:
                rule["left_date"] = rule.get("left")
            if rule.get("right_date") is None and rule.get("right") is not None:
                rule["right_date"] = rule.get("right")
        if rtype == "date_order":
            if rule.get("left") is None and rule.get("left_date") is not None:
                rule["left"] = rule.get("left_date")
            if rule.get("right") is None and rule.get("right_date") is not None:
                rule["right"] = rule.get("right_date")

        if rtype == "required_columns":
            cols = [str(c) for c in (rule.get("columns") or [])]
            missing = [c for c in cols if c not in df.columns]
            if missing:
                add_issue(rule=rule, msg=f"Missing required columns: {missing}")
            metrics[f"{rule['id']}.missing_columns"] = int(len(missing))
            continue

        if rtype == "pk_unique":
            pk = [str(c) for c in (rule.get("pk") or [])]
            missing = [c for c in pk if c not in df.columns]
            if missing:
                add_issue(rule=rule, msg=f"Missing PK columns: {missing}")
                metrics[f"{rule['id']}.missing_pk_columns"] = int(len(missing))
                continue
            key = df[pk].astype(str).agg("|".join, axis=1) if len(pk) > 1 else df[pk[0]].astype(str)
            dup = key[key.duplicated(keep=False)]
            metrics[f"{rule['id']}.duplicate_rows"] = int(len(dup))
            if len(dup) > 0:
                add_issue(rule=rule, msg=f"Duplicate primary key detected. sample={dup.iloc[0]}")
            continue

        if rtype == "non_null":
            col = str(rule.get("column"))
            if col not in df.columns:
                add_issue(rule=rule, msg=f"Column not found: {col}")
                continue
            miss = df[col].isna() | (df[col].astype("string").str.strip() == "")
            bad_idx = miss[miss].index[:rule_limit()]
            metrics[f"{rule['id']}.missing_rows"] = int(miss.sum())
            for idx in bad_idx:
                add_issue(rule=rule, msg=f"Required value is missing: {col}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=col)
            continue

        if rtype == "numeric_range":
            col = str(rule.get("column"))
            if col not in df.columns:
                add_issue(rule=rule, msg=f"Column not found: {col}")
                continue
            vmin = rule.get("min")
            vmax = rule.get("max")
            s = pd.to_numeric(df[col], errors="coerce")
            mask = pd.Series([False] * len(df), index=df.index)
            if vmin is not None:
                mask = mask | (s < float(vmin))
            if vmax is not None:
                mask = mask | (s > float(vmax))
            mask = mask & (~s.isna())
            metrics[f"{rule['id']}.out_of_range_rows"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                add_issue(rule=rule, msg=f"Out of range: {col} not in [{vmin},{vmax}]", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=col, sample_value=_as_str(df.loc[idx, col]))
            continue

        if rtype == "date_not_future":
            col = str(rule.get("column"))
            if col not in df.columns:
                add_issue(rule=rule, msg=f"Column not found: {col}")
                continue
            d = _to_date_series(df[col])
            mask = d.notna() & (d > today)
            metrics[f"{rule['id']}.future_rows"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                add_issue(rule=rule, msg=f"Future date not allowed: {col}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=col, sample_value=_as_str(df.loc[idx, col]))
            continue

        if rtype == "date_order":
            left = str(rule.get("left"))
            right = str(rule.get("right"))
            if left not in df.columns or right not in df.columns:
                add_issue(rule=rule, msg=f"Columns not found: {left} or {right}")
                continue
            dl = _to_date_series(df[left])
            dr = _to_date_series(df[right])
            mask = dl.notna() & dr.notna() & (dl > dr)
            metrics[f"{rule['id']}.violations"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                add_issue(rule=rule, msg=f"Date order violation: {left} must be <= {right}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=f"{left}>{right}", sample_value=f"{_as_str(df.loc[idx, left])}>{_as_str(df.loc[idx, right])}")
            continue

        if rtype == "join_date_order":
            left_on = [str(c) for c in (rule.get("left_on") or [])]
            right_on = [str(c) for c in (rule.get("right_on") or [])]
            left_date = str(rule.get("left_date"))
            right_ds = str(rule.get("right_dataset"))
            right_date = str(rule.get("right_date"))
            missing = [c for c in left_on + [left_date] if c not in df.columns]
            if missing:
                add_issue(rule=rule, msg=f"Missing columns: {missing}")
                continue
            rdf = get_df(right_ds)
            if rdf is None:
                continue
            missing_r = [c for c in right_on + [right_date] if c not in rdf.columns]
            if missing_r:
                add_issue(rule=rule, msg=f"Missing right columns in {right_ds}: {missing_r}")
                continue
            l = df[left_on + [left_date]].copy()
            r = rdf[right_on + [right_date]].copy()
            if left_on != right_on:
                rename = {rk: lk for rk, lk in zip(right_on, left_on)}
                r = r.rename(columns=rename)
            joined = l.merge(r, on=left_on, how="left", suffixes=("", "_r"))
            dl = _to_date_series(joined[left_date])
            dr = _to_date_series(joined[right_date])
            mask = dl.notna() & dr.notna() & (dl < dr)
            metrics[f"{rule['id']}.violations"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                add_issue(rule=rule, msg=f"Join date order violation: {left_date} must be >= {right_ds}.{right_date}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=f"{left_date}<{right_date}", sample_value=f"{_as_str(joined.loc[idx, left_date])}<{_as_str(joined.loc[idx, right_date])}")
            continue

        if rtype == "allowed_values":
            col = str(rule.get("column"))
            allowed = [str(v) for v in (rule.get("allowed_values") or [])]
            if col not in df.columns:
                add_issue(rule=rule, msg=f"Column not found: {col}")
                continue
            if not allowed:
                continue
            s = df[col].astype("string").str.strip()
            mask = s.notna() & (s != "") & (~s.isin(set(allowed)))
            metrics[f"{rule['id']}.invalid_values"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                add_issue(rule=rule, msg=f"Value not allowed for {col}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=col, sample_value=_as_str(df.loc[idx, col]))
            continue

        if rtype == "interval_overlap":
            group_cols = [str(c) for c in (rule.get("group_cols") or [])]
            start_col = str(rule.get("start"))
            end_col = str(rule.get("end"))
            missing = [c for c in group_cols + [start_col, end_col] if c not in df.columns]
            if missing:
                add_issue(rule=rule, msg=f"Missing columns: {missing}")
                continue
            d = df.copy()
            d["__s"] = _to_date_series(d[start_col])
            d["__e"] = _to_date_series(d[end_col])
            d.loc[d["__e"].isna(), "__e"] = d.loc[d["__e"].isna(), "__s"]
            d = d[d["__s"].notna()].copy()
            if d.empty:
                continue
            bad_rows: list[int] = []
            for _, g in d.groupby(group_cols, dropna=False):
                g = g.sort_values(["__s", "__e"])
                prev_end = None
                prev_idx = None
                for idx, row in g.iterrows():
                    if prev_end is not None and row["__s"] <= prev_end:
                        bad_rows.append(int(idx))
                        if prev_idx is not None:
                            bad_rows.append(int(prev_idx))
                    prev_end = row["__e"] if prev_end is None else max(prev_end, row["__e"])
                    prev_idx = idx
                    if len(set(bad_rows)) >= rule_limit():
                        break
                if len(set(bad_rows)) >= rule_limit():
                    break
            metrics[f"{rule['id']}.overlap_rows"] = int(len(set(bad_rows)))
            for idx in list(dict.fromkeys(bad_rows))[:rule_limit()]:
                add_issue(rule=rule, msg=f"Interval overlap detected within group {group_cols}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=f"{start_col}..{end_col}", sample_value=f"{_as_str(df.loc[idx, start_col])}..{_as_str(df.loc[idx, end_col])}")
            continue

        if rtype == "fk_exists":
            child_col = str(rule.get("child_column"))
            parent_ds = str(rule.get("parent_dataset"))
            parent_col = str(rule.get("parent_column"))
            if child_col not in df.columns:
                add_issue(rule=rule, msg=f"Column not found: {child_col}")
                continue
            pdf = get_df(parent_ds)
            if pdf is None or parent_col not in pdf.columns:
                continue
            parent_set = set(pdf[parent_col].dropna().astype(str).tolist())
            s = df[child_col].dropna().astype(str)
            mask = ~s.isin(parent_set)
            metrics[f"{rule['id']}.missing_fk_rows"] = int(mask.sum())
            for idx in mask[mask].index[:rule_limit()]:
                val = _as_str(df.loc[idx, child_col])
                add_issue(rule=rule, msg=f"FK not found: {child_col}='{val}' missing in {parent_ds}.{parent_col}", row_id=_row_id(df, int(idx), rule.get("row_id_cols")), field=child_col, sample_value=val)
            continue

        if rtype == "group_size_min":
            group_cols = [str(c) for c in (rule.get("group_cols") or [])]
            min_size = int(rule.get("min_size") or 1)
            missing = [c for c in group_cols if c not in df.columns]
            if missing:
                add_issue(rule=rule, msg=f"Missing group columns: {missing}")
                continue
            g = df.groupby(group_cols, dropna=False).size().reset_index(name="n")
            bad = g[g["n"] < min_size].head(rule_limit())
            metrics[f"{rule['id']}.small_groups"] = int(len(bad))
            for _, row in bad.iterrows():
                key = "|".join([str(row[c]) for c in group_cols])
                add_issue(rule=rule, msg=f"Small group size: n<{min_size}", row_id=key, field="group", sample_value=str(int(row["n"])))
            continue

        add_issue(rule=rule, msg=f"Unknown rule type: {rtype}")

    has_blocker = any(i.severity == "BLOCKER" for i in issues)
    has_major = any(i.severity == "MAJOR" for i in issues)
    qc_status = "ERROR" if has_blocker else ("WARN" if has_major else "PASS")

    farms_df = get_df("dm_farms")
    if farms_df is not None and "farm_id" in farms_df.columns:
        farm_ids = [str(x) for x in farms_df["farm_id"].dropna().astype(str).unique().tolist()]
    else:
        farm_ids = ["unknown_farm"]

    rule_by_id = {str(r["id"]): r for r in rules}
    for iss in issues:
        rule = rule_by_id.get(iss.rule_id)
        if not rule or not _rule_alert_template(rule):
            continue
        entity_type = str((_rule_alert_template(rule) or {}).get("entity_type") or "farm")
        entity_id = iss.row_id if entity_type != "farm" and iss.row_id else None
        farm_for_alert = None
        if iss.row_id and "|" in iss.row_id:
            farm_for_alert = iss.row_id.split("|")[0]
        if farm_for_alert is None:
            for fid in farm_ids:
                maybe_create_alert(rule, farm_id=fid, message=iss.message, entity_type=entity_type, entity_id=entity_id)
        else:
            maybe_create_alert(rule, farm_id=farm_for_alert, message=iss.message, entity_type=entity_type, entity_id=entity_id)

    issue_rows = [i.to_dict() for i in issues]
    issue_counts = build_issue_counts(pd.DataFrame(issue_rows))
    row_counts = build_row_counts(pd.DataFrame(issue_rows))

    return {
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": qc_status,
        "config_path": cfg.path,
        "config_version": cfg.config_version,
        "rules_sha256": cfg.rules_sha256,
        "rules_count": cfg.rules_count,
        "datasets_loaded": datasets_loaded,
        "issue_counts": issue_counts,
        "row_counts": row_counts,
        "counts": {
            "issues_total": len(issues),
            "issues_blocker": sum(1 for i in issues if i.severity == "BLOCKER"),
            "issues_major": sum(1 for i in issues if i.severity == "MAJOR"),
            "issues_minor": sum(1 for i in issues if i.severity == "MINOR"),
            "alerts_auto": len(alerts),
        },
        "metrics": metrics,
        "generated_at": _utc_ts(),
        "issues": issues,
        "alerts": alerts,
    }


def run_qc_rules(
    *,
    artifacts_root: Path,
    data_version: str,
    rules_path: Path,
    out_dir: Path,
    qc_run: Optional[str] = None,
    tenant_id: str = "default",
    max_issue_rows_per_rule: int = 200,
    manifest_type: str = "qc2",
) -> dict[str, Any]:
    qc_run = qc_run or new_qc_run_id()
    evaluated = evaluate_rule_based_qc(
        artifacts_root=artifacts_root,
        data_version=data_version,
        rules_path=rules_path,
        qc_run=qc_run,
        tenant_id=tenant_id,
        max_issue_rows_per_rule=max_issue_rows_per_rule,
    )
    summary = {
        "schema": "genomeai.qc_summary.v2",
        "created_at_utc": evaluated["generated_at"],
        "generated_at": evaluated["generated_at"],
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": evaluated["qc_status"],
        "config_path": evaluated["config_path"],
        "config_version": evaluated["config_version"],
        "rules_sha256": evaluated["rules_sha256"],
        "datasets_loaded": evaluated["datasets_loaded"],
        "issue_counts": evaluated["issue_counts"],
        "row_counts": evaluated["row_counts"],
        "metrics": evaluated["metrics"],
        "counts": evaluated["counts"],
    }
    result = write_qc_output_bundle(
        out_dir=out_dir,
        summary=summary,
        issues=evaluated["issues"],
        alerts=evaluated["alerts"],
        include_alerts_csv=True,
        include_bad_rows_detailed=False,
        manifest_type=manifest_type,
    )
    return {
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": evaluated["qc_status"],
        "config_version": evaluated["config_version"],
        "outputs": dict(result.get("outputs") or {}),
        "datasets_loaded": evaluated["datasets_loaded"],
        "issue_counts": evaluated["issue_counts"],
        "row_counts": evaluated["row_counts"],
        "metrics": evaluated["metrics"],
    }
