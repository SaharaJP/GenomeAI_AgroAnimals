from __future__ import annotations

"""T6-01 Pedigree QC + инбридинг-ограничения (v1, без геномики).

Политика:
- Никаких диагнозов.
- Только проверка качества родословной и объяснимые запреты на пары при общих предках.
- Web слой ничего не считает; он вызывает CLI/функции из этого модуля.

Артефакты:
  artifacts/<data_version>/pedigree/<pedigree_run>/
    - qc_issues.csv
    - alerts_auto.csv
    - inbreeding_constraints.csv
    - summary.json

Входные данные (канонический слой):
- dm_animals.csv  (animal_id, farm_id, sire_animal_id, dam_animal_id, sex...)
- dm_bulls.csv    (bull_id, farm_id...)

Если dm_bulls отсутствует, ограничения на пары не строим (только QC).
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

from .versioning import generate_run_id, write_json, write_checksums


DEFAULT_CFG_PATH = Path("configs/pedigree/pedigree_rules_v1.yaml")


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_canonical_dir(artifacts_root: Path, data_version: str) -> Path:
    """Support both layouts:
    - artifacts/<data_version>/canonical (legacy MVP)
    - artifacts/canonical/<data_version> (Target/web fixtures)
    """
    p1 = artifacts_root / data_version / "canonical"
    p2 = artifacts_root / "canonical" / data_version
    if p2.exists():
        return p2
    return p1


def _read_canonical_table(canonical_dir: Path, dataset: str) -> pd.DataFrame:
    pq = canonical_dir / f"{dataset}.parquet"
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    csv = canonical_dir / f"{dataset}.csv"
    if csv.exists():
        return pd.read_csv(csv)
    return pd.DataFrame()


def _load_cfg(path: Path = DEFAULT_CFG_PATH) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _norm_id(x: Any, unknown_tokens: Set[str]) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x).strip()
    if s.upper() in unknown_tokens:
        return None
    if s in unknown_tokens:
        return None
    return s if s != "" else None


@dataclass(frozen=True)
class PedigreeIssue:
    pedigree_run: str
    data_version: str
    rule_id: str
    severity: str
    farm_id: Optional[str]
    animal_id: Optional[str]
    message: str
    remediation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pedigree_run": self.pedigree_run,
            "data_version": self.data_version,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "farm_id": self.farm_id,
            "animal_id": self.animal_id,
            "message": self.message,
            "remediation": self.remediation,
        }


def _detect_cycles(parent_map: Dict[str, Tuple[Optional[str], Optional[str]]]) -> List[List[str]]:
    """Return list of cycles (each is node sequence).

    parent_map: child -> (sire, dam)
    """
    cycles: List[List[str]] = []
    state: Dict[str, int] = {}  # 0=unseen,1=visiting,2=done
    stack: List[str] = []
    pos: Dict[str, int] = {}

    def dfs(u: str) -> None:
        state[u] = 1
        pos[u] = len(stack)
        stack.append(u)
        sire, dam = parent_map.get(u, (None, None))
        for v in [sire, dam]:
            if v is None:
                continue
            if v not in parent_map:
                continue
            st = state.get(v, 0)
            if st == 0:
                dfs(v)
            elif st == 1:
                # cycle found: v .. u
                i = pos.get(v, 0)
                cyc = stack[i:] + [v]
                cycles.append(cyc)
        stack.pop()
        pos.pop(u, None)
        state[u] = 2

    for node in list(parent_map.keys()):
        if state.get(node, 0) == 0:
            dfs(node)
    # de-dup cycles by normalized signature
    uniq: Dict[str, List[str]] = {}
    for c in cycles:
        if len(c) < 2:
            continue
        sig = "|".join(sorted(set(c)))
        uniq.setdefault(sig, c)
    return list(uniq.values())


def _ancestors_upto(
    animal_id: str,
    parent_map: Dict[str, Tuple[Optional[str], Optional[str]]],
    *,
    generations: int,
    memo: Dict[Tuple[str, int], Dict[str, int]],
) -> Dict[str, int]:
    """Return ancestors with min depth (1..generations)."""
    key = (animal_id, generations)
    if key in memo:
        return memo[key]
    out: Dict[str, int] = {}
    frontier: List[Tuple[str, int]] = [(animal_id, 0)]
    seen: Set[str] = {animal_id}
    while frontier:
        u, d = frontier.pop(0)
        if d >= generations:
            continue
        sire, dam = parent_map.get(u, (None, None))
        for v in [sire, dam]:
            if v is None:
                continue
            if v in seen:
                continue
            seen.add(v)
            out[v] = min(out.get(v, 10**9), d + 1)
            frontier.append((v, d + 1))
    memo[key] = out
    return out


def _confidence_for_pair(
    cow_id: str,
    bull_id: str,
    parent_map: Dict[str, Tuple[Optional[str], Optional[str]]],
    *,
    generations: int,
) -> Tuple[str, Dict[str, Any]]:
    """Heuristic confidence: depends on completeness of pedigree graph."""

    def completeness(a: str) -> float:
        # count known parents in first generation only (cheap heuristic)
        sire, dam = parent_map.get(a, (None, None))
        known = 0
        total = 0
        for v in [sire, dam]:
            total += 1
            if v is not None:
                known += 1
        return known / total if total > 0 else 0.0

    if bull_id not in parent_map:
        return "LOW", {"reason": "bull_not_in_pedigree"}
    c1 = completeness(cow_id) if cow_id in parent_map else 0.0
    b1 = completeness(bull_id)
    # very rough: if both have both parents -> HIGH
    if c1 >= 0.99 and b1 >= 0.99:
        return "HIGH", {"cow_gen1_known": c1, "bull_gen1_known": b1}
    if c1 >= 0.5 and b1 >= 0.5:
        return "MEDIUM", {"cow_gen1_known": c1, "bull_gen1_known": b1}
    return "LOW", {"cow_gen1_known": c1, "bull_gen1_known": b1}


def run_pedigree_qc(
    *,
    artifacts_root: Path,
    data_version: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    pedigree_run: Optional[str] = None,
    generations: Optional[int] = None,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Run pedigree QC + compute inbreeding constraints."""

    artifacts_root = Path(artifacts_root).resolve()
    canonical_dir = _resolve_canonical_dir(artifacts_root, data_version)
    if not canonical_dir.exists():
        return {"ok": False, "reason": "canonical_dir_missing", "data_version": data_version}

    cfg = _load_cfg(cfg_path)
    unknown_tokens = set([str(x).strip().upper() for x in (cfg.get("unknown_parent_tokens") or [])])
    qc_cfg = cfg.get("qc") or {}
    ib_cfg = cfg.get("inbreeding") or {}

    missing_parent_pct_warn = float(qc_cfg.get("missing_parent_pct_warn", 0.2))
    max_issues_per_rule = int(qc_cfg.get("max_issues_per_rule", 200))
    sev_map = qc_cfg.get("severity") or {}

    generations_cfg = int(ib_cfg.get("generations", 3))
    generations = int(generations) if generations is not None else generations_cfg
    prohibit_if_common = bool(ib_cfg.get("prohibit_if_common_ancestor", True))
    max_common_list = int(ib_cfg.get("max_common_ancestors_list", 5))
    allow_if_bull_missing = bool(ib_cfg.get("allow_if_bull_missing_pedigree", True))

    pedigree_run = pedigree_run or generate_run_id("pedigree")
    out_dir = artifacts_root / data_version / "pedigree" / pedigree_run
    out_dir.mkdir(parents=True, exist_ok=True)

    animals = _read_canonical_table(canonical_dir, "dm_animals")
    bulls = _read_canonical_table(canonical_dir, "dm_bulls")

    if animals.empty:
        write_json(out_dir / "summary.json", {"ok": False, "reason": "dm_animals_missing", "data_version": data_version})
        return {"ok": False, "reason": "dm_animals_missing", "data_version": data_version}

    # normalize key columns (best-effort across vendors)
    col_animal = "animal_id" if "animal_id" in animals.columns else "source_animal_id" if "source_animal_id" in animals.columns else None
    if not col_animal:
        write_json(out_dir / "summary.json", {"ok": False, "reason": "animal_id_column_missing", "data_version": data_version})
        return {"ok": False, "reason": "animal_id_column_missing", "data_version": data_version}

    col_farm = "farm_id" if "farm_id" in animals.columns else None
    col_sire = "sire_animal_id" if "sire_animal_id" in animals.columns else "sire_id" if "sire_id" in animals.columns else None
    col_dam = "dam_animal_id" if "dam_animal_id" in animals.columns else "dam_id" if "dam_id" in animals.columns else None
    col_sex = "sex" if "sex" in animals.columns else None

    a = animals.copy()
    if col_farm is None:
        a["farm_id"] = pd.NA
        col_farm = "farm_id"

    a["animal_id_norm"] = a[col_animal].astype("string").str.strip()
    a["farm_id_norm"] = a[col_farm].astype("string").str.strip()

    if col_sire:
        a["sire_norm"] = a[col_sire].apply(lambda x: _norm_id(x, unknown_tokens))
    else:
        a["sire_norm"] = None
    if col_dam:
        a["dam_norm"] = a[col_dam].apply(lambda x: _norm_id(x, unknown_tokens))
    else:
        a["dam_norm"] = None

    # drop rows without animal id
    a = a.dropna(subset=["animal_id_norm"])

    issues: List[PedigreeIssue] = []

    def add_issue(rule_id: str, severity: str, farm_id: Optional[str], animal_id: Optional[str], message: str, remediation: str) -> None:
        if len([i for i in issues if i.rule_id == rule_id]) >= max_issues_per_rule:
            return
        issues.append(
            PedigreeIssue(
                pedigree_run=pedigree_run,
                data_version=data_version,
                rule_id=rule_id,
                severity=severity,
                farm_id=farm_id,
                animal_id=animal_id,
                message=message,
                remediation=remediation,
            )
        )

    # rule P001: missing parents rate per farm
    for farm_id, g in a.groupby("farm_id_norm", dropna=False):
        n = len(g)
        if n <= 0:
            continue
        miss_sire = float(g["sire_norm"].isna().mean())
        miss_dam = float(g["dam_norm"].isna().mean())
        if miss_sire >= missing_parent_pct_warn or miss_dam >= missing_parent_pct_warn:
            add_issue(
                "P001_MISSING_PARENTS_FARM",
                str(sev_map.get("missing_parents_farm", "MINOR")),
                str(farm_id) if pd.notna(farm_id) else None,
                None,
                f"Высокая доля пропусков родителей: sire_missing={miss_sire:.0%}, dam_missing={miss_dam:.0%} (n={n})",
                "Заполнить sire/dam в племучёте и повторить импорт dm_animals.",
            )

    # rule P002: unknown parent references
    known_animals = set(a["animal_id_norm"].dropna().astype(str).tolist())
    for _, r in a.iterrows():
        fid = r.get("farm_id_norm")
        aid = r.get("animal_id_norm")
        for parent_col, role in [("sire_norm", "sire"), ("dam_norm", "dam")]:
            pid = r.get(parent_col)
            if pid is None or (isinstance(pid, float) and pd.isna(pid)):
                continue
            if str(pid) not in known_animals:
                add_issue(
                    "P002_UNKNOWN_PARENT_REF",
                    str(sev_map.get("unknown_parent_ref", "MINOR")),
                    str(fid) if pd.notna(fid) else None,
                    str(aid) if pd.notna(aid) else None,
                    f"{role}={pid} отсутствует в dm_animals",
                    "Проверить ID родителя на опечатки или добавить родителя в dm_animals.",
                )

    # rule P003: duplicate animal_id with conflicting parents
    dup = a.groupby(["farm_id_norm", "animal_id_norm"], dropna=False).agg(
        sire_n=("sire_norm", lambda x: len(set([z for z in x if z is not None]))),
        dam_n=("dam_norm", lambda x: len(set([z for z in x if z is not None]))),
        rows=("animal_id_norm", "size"),
    )
    for (fid, aid), row in dup.iterrows():
        if int(row["rows"]) <= 1:
            continue
        if int(row["sire_n"]) > 1 or int(row["dam_n"]) > 1:
            add_issue(
                "P003_DUPLICATE_CONFLICT",
                str(sev_map.get("duplicate_conflict", "MAJOR")),
                str(fid) if pd.notna(fid) else None,
                str(aid) if pd.notna(aid) else None,
                f"Найдено {int(row['rows'])} строк по animal_id с конфликтующими sire/dam",
                "Устранить дубликаты animal_id или привести sire/dam к единому значению.",
            )

    # rule P004: self-parent
    for _, r in a.iterrows():
        fid = r.get("farm_id_norm")
        aid = str(r.get("animal_id_norm"))
        if r.get("sire_norm") == aid or r.get("dam_norm") == aid:
            add_issue(
                "P004_SELF_PARENT",
                str(sev_map.get("self_parent", "MAJOR")),
                str(fid) if pd.notna(fid) else None,
                aid,
                "Животное указано как собственный родитель (sire/dam == animal_id)",
                "Исправить ошибочную связь sire/dam.",
            )

    # rule P005: cycles (per farm)
    cycles_total = 0
    for fid, g in a.groupby("farm_id_norm", dropna=False):
        pm: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for _, r in g.iterrows():
            aid = str(r.get("animal_id_norm"))
            pm[aid] = (r.get("sire_norm"), r.get("dam_norm"))
        cycles = _detect_cycles(pm)
        for cyc in cycles:
            cycles_total += 1
            # report on the first node in cycle to avoid spam
            add_issue(
                "P005_CYCLE",
                str(sev_map.get("cycle", "MAJOR")),
                str(fid) if pd.notna(fid) else None,
                str(cyc[0]) if cyc else None,
                f"Цикл в родословной: {' -> '.join([str(x) for x in cyc[:10]])}{' ...' if len(cyc) > 10 else ''}",
                "Исправить связи sire/dam для разрыва цикла.",
            )

    # build inbreeding constraints (cows x bulls) per farm
    constraints_rows: List[Dict[str, Any]] = []
    memo: Dict[Tuple[str, int], Dict[str, int]] = {}

    # parent_map per farm
    for fid, g in a.groupby("farm_id_norm", dropna=False):
        pm: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for _, r in g.iterrows():
            aid = str(r.get("animal_id_norm"))
            pm[aid] = (r.get("sire_norm"), r.get("dam_norm"))

        # cows: if sex column exists, keep F/U; else keep all
        if col_sex and col_sex in g.columns:
            gg = g.copy()
            s = gg[col_sex].astype("string").str.upper()
            cows = gg.loc[~(s == "M"), "animal_id_norm"].astype("string").tolist()
        else:
            cows = g["animal_id_norm"].astype("string").tolist()

        bulls_farm: List[str] = []
        if not bulls.empty:
            bcol = "bull_id" if "bull_id" in bulls.columns else "animal_id" if "animal_id" in bulls.columns else None
            if bcol:
                bb = bulls.copy()
                if "farm_id" in bb.columns:
                    bb["farm_id_norm"] = bb["farm_id"].astype("string").str.strip()
                    bb = bb.loc[bb["farm_id_norm"].astype("string") == str(fid)]
                bulls_farm = bb[bcol].astype("string").str.strip().dropna().tolist()

        for cow_id in cows:
            cow_id_s = str(cow_id)
            anc_cow = _ancestors_upto(cow_id_s, pm, generations=generations, memo=memo)
            for bull_id in bulls_farm:
                bull_id_s = str(bull_id)
                if bull_id_s not in pm:
                    if allow_if_bull_missing:
                        conf, conf_meta = _confidence_for_pair(cow_id_s, bull_id_s, pm, generations=generations)
                        constraints_rows.append(
                            {
                                "data_version": data_version,
                                "pedigree_run": pedigree_run,
                                "farm_id": str(fid) if pd.notna(fid) else None,
                                "cow_id": cow_id_s,
                                "bull_id": bull_id_s,
                                "allowed": True,
                                "reason_code": "BULL_PEDIGREE_MISSING",
                                "common_ancestors": "",
                                "min_common_depth": None,
                                "confidence": conf,
                                "confidence_meta": json.dumps(conf_meta, ensure_ascii=False),
                            }
                        )
                    else:
                        constraints_rows.append(
                            {
                                "data_version": data_version,
                                "pedigree_run": pedigree_run,
                                "farm_id": str(fid) if pd.notna(fid) else None,
                                "cow_id": cow_id_s,
                                "bull_id": bull_id_s,
                                "allowed": False,
                                "reason_code": "BULL_PEDIGREE_MISSING",
                                "common_ancestors": "",
                                "min_common_depth": None,
                                "confidence": "LOW",
                                "confidence_meta": json.dumps({"reason": "bull_not_in_pedigree"}, ensure_ascii=False),
                            }
                        )
                    continue

                anc_bull = _ancestors_upto(bull_id_s, pm, generations=generations, memo=memo)
                common = set(anc_cow.keys()) & set(anc_bull.keys())
                if prohibit_if_common and len(common) > 0:
                    # choose top k common by min depth
                    common_list = sorted(
                        list(common),
                        key=lambda x: min(anc_cow.get(x, 10**9), anc_bull.get(x, 10**9)),
                    )[:max_common_list]
                    min_depth = None
                    for x in common_list:
                        d = min(anc_cow.get(x, 10**9), anc_bull.get(x, 10**9))
                        min_depth = d if min_depth is None else min(min_depth, d)
                    conf, conf_meta = _confidence_for_pair(cow_id_s, bull_id_s, pm, generations=generations)
                    constraints_rows.append(
                        {
                            "data_version": data_version,
                            "pedigree_run": pedigree_run,
                            "farm_id": str(fid) if pd.notna(fid) else None,
                            "cow_id": cow_id_s,
                            "bull_id": bull_id_s,
                            "allowed": False,
                            "reason_code": "COMMON_ANCESTOR_WITHIN_N",
                            "common_ancestors": ",".join(common_list),
                            "min_common_depth": min_depth,
                            "confidence": conf,
                            "confidence_meta": json.dumps(conf_meta, ensure_ascii=False),
                        }
                    )
                else:
                    conf, conf_meta = _confidence_for_pair(cow_id_s, bull_id_s, pm, generations=generations)
                    constraints_rows.append(
                        {
                            "data_version": data_version,
                            "pedigree_run": pedigree_run,
                            "farm_id": str(fid) if pd.notna(fid) else None,
                            "cow_id": cow_id_s,
                            "bull_id": bull_id_s,
                            "allowed": True,
                            "reason_code": "OK",
                            "common_ancestors": "",
                            "min_common_depth": None,
                            "confidence": conf,
                            "confidence_meta": json.dumps(conf_meta, ensure_ascii=False),
                        }
                    )

    # write qc_issues.csv
    df_issues = pd.DataFrame([i.to_dict() for i in issues])
    qc_issues_csv = out_dir / "qc_issues.csv"
    df_issues.to_csv(qc_issues_csv, index=False)

    # auto alerts (qc issues -> alert candidates)
    today = date.today().isoformat()
    alerts_rows: List[Dict[str, Any]] = []

    def _alert_id(rule_id: str, farm_id: Optional[str], animal_id: Optional[str]) -> str:
        suffix = f"{farm_id or ''}|{animal_id or ''}|{rule_id}"
        h = hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:10]
        return f"al_{h}"

    for i in issues:
        if i.rule_id == "P001_MISSING_PARENTS_FARM":
            alert_type = "PEDIGREE.MISSING_PARENTS"
            entity_type = "farm"
            entity_id = i.farm_id
        elif i.rule_id == "P002_UNKNOWN_PARENT_REF":
            alert_type = "PEDIGREE.UNKNOWN_PARENT_REF"
            entity_type = "animal"
            entity_id = i.animal_id
        elif i.rule_id in {"P003_DUPLICATE_CONFLICT", "P004_SELF_PARENT"}:
            alert_type = "PEDIGREE.CONFLICT"
            entity_type = "animal"
            entity_id = i.animal_id
        elif i.rule_id == "P005_CYCLE":
            alert_type = "PEDIGREE.CYCLE"
            entity_type = "animal"
            entity_id = i.animal_id
        else:
            alert_type = "QC.GENERIC"
            entity_type = "dataset"
            entity_id = "dm_animals"

        alerts_rows.append(
            {
                "tenant_id": tenant_id,
                "alert_id": _alert_id(i.rule_id, i.farm_id, i.animal_id),
                "farm_id": i.farm_id,
                "alert_date": today,
                "severity": i.severity,
                "alert_type": alert_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "message": i.message,
                "source_rule_id": i.rule_id,
                "qc_run": pedigree_run,
                "data_version": data_version,
            }
        )

    alerts_auto_csv = out_dir / "alerts_auto.csv"
    pd.DataFrame(alerts_rows).to_csv(alerts_auto_csv, index=False)

    # write inbreeding constraints
    constraints_csv = out_dir / "inbreeding_constraints.csv"
    pd.DataFrame(constraints_rows).to_csv(constraints_csv, index=False)

    summary = {
        "ok": True,
        "tool": "pedigree_qc",
        "schema": "genomeai.pedigree_qc.v1",
        "created_at_utc": _utc_ts(),
        "data_version": data_version,
        "pedigree_run": pedigree_run,
        "inputs": {
            "canonical_dir": str(canonical_dir),
            "cfg_path": str(cfg_path),
        },
        "stats": {
            "issues": int(len(df_issues)),
            "cycles_reported": int(cycles_total),
            "constraints_rows": int(len(constraints_rows)),
            "generations": generations,
        },
        "outputs": {
            "qc_issues_csv": str(qc_issues_csv),
            "alerts_auto_csv": str(alerts_auto_csv),
            "constraints_csv": str(constraints_csv),
        },
        "limitations": [
            "Если бык отсутствует в dm_animals, ограничения считаются с LOW confidence (или разрешаются, см. config).",
            "v1 не вычисляет коэффициент инбридинга (F) — только запреты по общим предкам до N поколений.",
        ],
    }
    write_json(out_dir / "summary.json", summary)

    # checksums for repeatability
    write_checksums(run_root=out_dir, include_subdirs=None)

    return summary
