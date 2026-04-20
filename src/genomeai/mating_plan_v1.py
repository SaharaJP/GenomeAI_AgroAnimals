from __future__ import annotations

"""T6-02: Mating plan v1 (decision-support).

Назначение:
 - Вход: коровы-кандидаты, быки, ограничения по родству (T6-01), простые правила
 - Выход: для каждой коровы 3-5 быков + причины/уверенность
 - Никаких запрещённых пар.

Артефакты:
  artifacts/<data_version>/mating_plan/<mating_plan_run>/
    - mating_plan.csv
    - mating_plan.xlsx
    - summary.json
    - checksums.sha256

Важно:
 - Web/Streamlit слой не "считает" подбор; он вызывает функции из этого модуля.
 - В v1 мы не решаем задачу оптимизации по стаду; это ранжирование по понятным правилам.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .versioning import generate_run_id, write_checksums, write_json


DEFAULT_CFG_PATH = Path("configs/mating_plan/mating_plan_v1.yaml")


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_canonical_dir(artifacts_root: Path, data_version: str) -> Path:
    # keep consistent with pedigree_qc.py
    p1 = artifacts_root / data_version / "canonical"
    p2 = artifacts_root / "canonical" / data_version
    if p2.exists():
        return p2
    return p1


def _read_table(canonical_dir: Path, dataset: str) -> pd.DataFrame:
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


def _load_cfg(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _latest_run_dir(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    # run ids are time-based; lexicographic sort is OK
    return sorted(dirs, key=lambda p: p.name)[-1]


def _safe_num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if pd.isna(v):
            return None
        return v
    except Exception:
        return None


def _zscore(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    mu = float(s.mean()) if s.notna().any() else 0.0
    sd = float(s.std(ddof=0)) if s.notna().any() else 0.0
    if sd <= 1e-9:
        return s * 0.0
    return (s - mu) / sd


@dataclass(frozen=True)
class PlanRow:
    tenant_id: str
    data_version: str
    mating_plan_run: str
    pedigree_run: str
    farm_id: Optional[str]
    cow_id: str
    bull_id: str
    rank: int
    score: float
    confidence: str
    reasons: str
    constraints_reason_code: str
    constraints_confidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "data_version": self.data_version,
            "mating_plan_run": self.mating_plan_run,
            "pedigree_run": self.pedigree_run,
            "farm_id": self.farm_id,
            "cow_id": self.cow_id,
            "bull_id": self.bull_id,
            "rank": int(self.rank),
            "score": float(self.score),
            "confidence": self.confidence,
            "reasons": self.reasons,
            "constraints_reason_code": self.constraints_reason_code,
            "constraints_confidence": self.constraints_confidence,
        }


def _cow_candidates_from_repro(artifacts_root: Path, data_version: str) -> pd.DataFrame:
    repro_root = artifacts_root / data_version / "repro"
    latest = _latest_run_dir(repro_root)
    if not latest:
        return pd.DataFrame()
    wl = latest / "worklists.csv"
    if not wl.exists():
        return pd.DataFrame()
    df = pd.read_csv(wl)
    # keep only insemination/repeat
    if "worklist_type" in df.columns:
        df = df[df["worklist_type"].isin(["insemination", "repeat"])]
    # normalize
    if "cow_id" not in df.columns and "animal_id" in df.columns:
        df = df.rename(columns={"animal_id": "cow_id"})
    if "cow_id" not in df.columns:
        return pd.DataFrame()
    return df[[c for c in ["farm_id", "cow_id"] if c in df.columns]].dropna(subset=["cow_id"]).drop_duplicates()


def _pick_cows(
    *,
    animals: pd.DataFrame,
    artifacts_root: Path,
    data_version: str,
    source: str,
) -> pd.DataFrame:
    if animals.empty:
        return pd.DataFrame(columns=["farm_id", "cow_id"])

    # detect columns
    cow_id_col = "animal_id" if "animal_id" in animals.columns else "source_animal_id" if "source_animal_id" in animals.columns else None
    if not cow_id_col:
        return pd.DataFrame(columns=["farm_id", "cow_id"])
    farm_col = "farm_id" if "farm_id" in animals.columns else None
    sex_col = "sex" if "sex" in animals.columns else None

    if source == "repro_worklist":
        cand = _cow_candidates_from_repro(artifacts_root, data_version)
        if not cand.empty:
            # if farm_id missing in worklist, try to join from animals
            if "farm_id" not in cand.columns and farm_col:
                tmp = animals[[cow_id_col, farm_col]].copy()
                tmp = tmp.rename(columns={cow_id_col: "cow_id", farm_col: "farm_id"})
                cand = cand.merge(tmp, on="cow_id", how="left")
            if "farm_id" not in cand.columns:
                cand["farm_id"] = pd.NA
            return cand[["farm_id", "cow_id"]].drop_duplicates()
        # fallback
        source = "all_females"

    # all_females
    a = animals.copy()
    a = a.rename(columns={cow_id_col: "cow_id"})
    if farm_col and farm_col in a.columns:
        a = a.rename(columns={farm_col: "farm_id"})
    else:
        a["farm_id"] = pd.NA

    if sex_col and sex_col in a.columns:
        s = a[sex_col].astype("string").str.upper()
        a = a[~(s == "M")]
    return a[["farm_id", "cow_id"]].dropna(subset=["cow_id"]).drop_duplicates()


def _latest_pedigree_constraints(artifacts_root: Path, data_version: str) -> Tuple[Optional[str], Optional[Path]]:
    ped_root = artifacts_root / data_version / "pedigree"
    latest = _latest_run_dir(ped_root)
    if not latest:
        return None, None
    csv = latest / "inbreeding_constraints.csv"
    if not csv.exists():
        return None, None
    return latest.name, csv


def _compute_cow_features(animals: pd.DataFrame, lact: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    cows = animals.copy()
    cow_id_col = "animal_id" if "animal_id" in cows.columns else "source_animal_id" if "source_animal_id" in cows.columns else None
    if not cow_id_col:
        return pd.DataFrame()
    farm_col = "farm_id" if "farm_id" in cows.columns else None

    cows = cows.rename(columns={cow_id_col: "cow_id"})
    if farm_col and farm_col in cows.columns:
        cows = cows.rename(columns={farm_col: "farm_id"})
    else:
        cows["farm_id"] = pd.NA

    if lact.empty:
        base = cows[["farm_id", "cow_id"]].drop_duplicates()
        for c in ["milk_305d_kg", "fat_pct", "protein_pct", "scc"]:
            base[c] = pd.NA
        return base

    cc = (cfg.get("cow_lactation_columns") or {})
    col_cow = str(cc.get("cow_id", "animal_id"))
    col_farm = str(cc.get("farm_id", "farm_id"))
    col_date = str(cc.get("calving_date", "calving_date"))

    # numeric columns (optional)
    col_milk = str(cc.get("milk_305d_kg", "milk_305d_kg"))
    col_fat = str(cc.get("fat_pct", "fat_pct"))
    col_prot = str(cc.get("protein_pct", "protein_pct"))
    col_scc = str(cc.get("scc", "scc"))

    l = lact.copy()
    if col_cow not in l.columns:
        return cows[["farm_id", "cow_id"]].drop_duplicates()
    l["cow_id"] = l[col_cow].astype("string").str.strip()
    if col_farm in l.columns:
        l["farm_id"] = l[col_farm].astype("string").str.strip()
    else:
        l["farm_id"] = pd.NA
    if col_date in l.columns:
        l["calving_date"] = pd.to_datetime(l[col_date], errors="coerce")
    else:
        l["calving_date"] = pd.NaT
    # choose latest lactation
    l = l.sort_values(["cow_id", "calving_date"], ascending=[True, False])
    l1 = l.drop_duplicates(subset=["cow_id"], keep="first")

    out = l1[["cow_id", "farm_id"]].copy()
    out["milk_305d_kg"] = pd.to_numeric(l1[col_milk], errors="coerce") if col_milk in l1.columns else pd.NA
    out["fat_pct"] = pd.to_numeric(l1[col_fat], errors="coerce") if col_fat in l1.columns else pd.NA
    out["protein_pct"] = pd.to_numeric(l1[col_prot], errors="coerce") if col_prot in l1.columns else pd.NA
    out["scc"] = pd.to_numeric(l1[col_scc], errors="coerce") if col_scc in l1.columns else pd.NA

    # ensure we keep cows even without lactation record
    base = cows[["farm_id", "cow_id"]].drop_duplicates()
    out = base.merge(out, on=["farm_id", "cow_id"], how="left")
    return out


def _compute_bull_features(bulls: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    if bulls.empty:
        return pd.DataFrame()
    bc = (cfg.get("bull_columns") or {})
    col_id = str(bc.get("bull_id", "bull_id"))
    if col_id not in bulls.columns:
        return pd.DataFrame()
    col_farm = str(bc.get("farm_id", "farm_id"))

    b = bulls.copy()
    b["bull_id"] = b[col_id].astype("string").str.strip()
    if col_farm in b.columns:
        b["farm_id"] = b[col_farm].astype("string").str.strip()
    else:
        b["farm_id"] = pd.NA

    def num(col_key: str, default: str) -> pd.Series:
        c = str(bc.get(col_key, default))
        return pd.to_numeric(b[c], errors="coerce") if c in b.columns else pd.Series([pd.NA] * len(b))

    b["ebv_milk"] = num("ebv_milk", "ebv_milk")
    b["ebv_fat"] = num("ebv_fat", "ebv_fat")
    b["ebv_protein"] = num("ebv_protein", "ebv_protein")
    b["ebv_scc"] = num("ebv_scc", "ebv_scc")
    b["price"] = num("price", "dose_price")

    c_av = str(bc.get("available", "available"))
    if c_av in b.columns:
        s = b[c_av]
        # accept bool, 0/1, strings
        b["available"] = s.apply(lambda x: str(x).strip().lower() in {"1", "true", "yes", "y", "available"})
    else:
        b["available"] = True
    return b[["farm_id", "bull_id", "ebv_milk", "ebv_fat", "ebv_protein", "ebv_scc", "price", "available"]].drop_duplicates(subset=["bull_id"])


def _need_profile(cows: pd.DataFrame, threshold_z: float) -> pd.DataFrame:
    # per farm z-scores for milk and scc
    out = cows.copy()
    out["need_milk"] = False
    out["need_scc"] = False
    for fid, g in out.groupby("farm_id", dropna=False):
        if "milk_305d_kg" in g.columns:
            z = _zscore(g["milk_305d_kg"])
            out.loc[g.index, "need_milk"] = z <= -float(threshold_z)
        if "scc" in g.columns:
            z = _zscore(g["scc"])
            out.loc[g.index, "need_scc"] = z >= float(threshold_z)
    return out


def _score_bulls_for_cow(
    cow_row: pd.Series,
    bulls: pd.DataFrame,
    cfg: Dict[str, Any],
) -> pd.Series:
    w = cfg.get("weights") or {}
    nb = cfg.get("need_boost") or {}
    need_milk = bool(cow_row.get("need_milk"))
    need_scc = bool(cow_row.get("need_scc"))

    w_milk = float(w.get("milk", 1.0)) * (float(nb.get("milk", 1.0)) if need_milk else 1.0)
    w_fat = float(w.get("fat", 0.4))
    w_prot = float(w.get("protein", 0.4))
    w_scc = float(w.get("scc", 0.8)) * (float(nb.get("scc", 1.0)) if need_scc else 1.0)
    w_price = float(w.get("price", 0.0))

    z_milk = _zscore(bulls.get("ebv_milk"))
    z_fat = _zscore(bulls.get("ebv_fat"))
    z_prot = _zscore(bulls.get("ebv_protein"))
    z_scc = _zscore(bulls.get("ebv_scc"))
    z_price = _zscore(bulls.get("price"))

    # higher score = better
    # SCC: lower is better, поэтому минус
    score = (
        w_milk * z_milk.fillna(0.0)
        + w_fat * z_fat.fillna(0.0)
        + w_prot * z_prot.fillna(0.0)
        - w_scc * z_scc.fillna(0.0)
        - w_price * z_price.fillna(0.0)
    )
    return score


def _merge_constraints(
    plans: pd.DataFrame,
    constraints: pd.DataFrame,
) -> pd.DataFrame:
    if constraints.empty:
        plans["allowed"] = True
        plans["constraints_reason_code"] = "NO_CONSTRAINTS"
        plans["constraints_confidence"] = "LOW"
        return plans
    c = constraints.copy()
    # normalize
    for col in ["cow_id", "bull_id"]:
        if col in c.columns:
            c[col] = c[col].astype("string").str.strip()
    if "allowed" in c.columns:
        c["allowed"] = c["allowed"].astype(bool)
    else:
        c["allowed"] = True
    keep = c[["cow_id", "bull_id", "allowed", "reason_code", "confidence"]].rename(
        columns={"reason_code": "constraints_reason_code", "confidence": "constraints_confidence"}
    )
    out = plans.merge(keep, on=["cow_id", "bull_id"], how="left")
    out["allowed"] = out["allowed"].fillna(True)
    out["constraints_reason_code"] = out["constraints_reason_code"].fillna("OK")
    out["constraints_confidence"] = out["constraints_confidence"].fillna("LOW")
    return out


def _confidence(row: pd.Series) -> str:
    # base from constraints confidence
    base = str(row.get("constraints_confidence") or "LOW").upper()
    # degrade if missing EBVs
    missing = 0
    for c in ["ebv_milk", "ebv_fat", "ebv_protein", "ebv_scc"]:
        if pd.isna(row.get(c)):
            missing += 1
    if missing >= 3:
        return "LOW"
    if missing == 2 and base == "HIGH":
        return "MEDIUM"
    return base if base in {"HIGH", "MEDIUM", "LOW"} else "LOW"


def _reasons(cow: pd.Series, bull: pd.Series) -> str:
    parts: List[str] = []
    parts.append("Избежание родства: OK")
    if bool(cow.get("need_milk")):
        parts.append("Цель: увеличить удой")
    if bool(cow.get("need_scc")):
        parts.append("Цель: снизить SCC")
    # show bull highlights if present
    if pd.notna(bull.get("ebv_milk")):
        parts.append(f"EBV_milk={_safe_num(bull.get('ebv_milk')):.2f}")
    if pd.notna(bull.get("ebv_scc")):
        parts.append(f"EBV_scc={_safe_num(bull.get('ebv_scc')):.2f}")
    if pd.notna(bull.get("price")):
        parts.append(f"Цена={_safe_num(bull.get('price')):.0f}")
    return "; ".join([p for p in parts if p])


def run_mating_plan(
    *,
    artifacts_root: Path,
    data_version: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    mating_plan_run: Optional[str] = None,
    pedigree_run: Optional[str] = None,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Build mating plan artifacts for a given data_version."""

    artifacts_root = Path(artifacts_root).resolve()
    canonical_dir = _resolve_canonical_dir(artifacts_root, data_version)
    if not canonical_dir.exists():
        return {"ok": False, "reason": "canonical_dir_missing", "data_version": data_version}

    cfg = _load_cfg(cfg_path)
    mating_plan_run = mating_plan_run or generate_run_id("mating")

    animals = _read_table(canonical_dir, "dm_animals")
    bulls = _read_table(canonical_dir, "dm_bulls")
    lact = _read_table(canonical_dir, "dm_lactations")

    if animals.empty:
        return {"ok": False, "reason": "dm_animals_missing", "data_version": data_version}
    if bulls.empty:
        return {"ok": False, "reason": "dm_bulls_missing", "data_version": data_version}

    # constraints
    ped_run, constraints_path = _latest_pedigree_constraints(artifacts_root, data_version)
    if pedigree_run:
        ped_run = str(pedigree_run)
        constraints_path = artifacts_root / data_version / "pedigree" / ped_run / "inbreeding_constraints.csv"
        if not constraints_path.exists():
            constraints_path = None

    if not ped_run or not constraints_path:
        return {
            "ok": False,
            "reason": "pedigree_constraints_missing",
            "data_version": data_version,
            "hint": "Сначала выполните T6-01 (genomeai pedigree ...), чтобы получить inbreeding_constraints.csv",
        }

    constraints = pd.read_csv(constraints_path)

    cows_sel = _pick_cows(
        animals=animals,
        artifacts_root=artifacts_root,
        data_version=data_version,
        source=str(cfg.get("cow_candidates_source") or "repro_worklist"),
    )
    if cows_sel.empty:
        return {"ok": False, "reason": "no_cow_candidates", "data_version": data_version}

    cow_feat = _compute_cow_features(animals, lact, cfg)
    cow_feat = cow_feat.merge(cows_sel, on=["farm_id", "cow_id"], how="inner")
    cow_feat = _need_profile(cow_feat, float(cfg.get("need_threshold_z", 0.5)))

    bull_feat = _compute_bull_features(bulls, cfg)
    if bull_feat.empty:
        return {"ok": False, "reason": "dm_bulls_missing_fields", "data_version": data_version}

    # filters
    filt = cfg.get("filters") or {}
    if bool(filt.get("require_available", False)) and "available" in bull_feat.columns:
        bull_feat = bull_feat[bull_feat["available"] == True]
    max_price = filt.get("max_price")
    if max_price is not None:
        try:
            mp = float(max_price)
            bull_feat = bull_feat[pd.to_numeric(bull_feat["price"], errors="coerce") <= mp]
        except Exception:
            pass

    top_k = int(cfg.get("top_k_per_cow", 5))
    top_k = max(1, min(top_k, 10))

    rows: List[PlanRow] = []
    forbidden_cnt = 0
    total_candidates = 0

    # pre-index constraints by cow for speed
    constraints["cow_id"] = constraints["cow_id"].astype("string").str.strip()
    constraints["bull_id"] = constraints["bull_id"].astype("string").str.strip()
    constraints_allowed = constraints[constraints.get("allowed").astype(bool) == True] if "allowed" in constraints.columns else constraints

    # build allowed map per cow
    allowed_map: Dict[str, set[str]] = {}
    for cow_id, g in constraints_allowed.groupby("cow_id"):
        allowed_map[str(cow_id)] = set(g["bull_id"].astype(str).tolist())

    for _, cow in cow_feat.iterrows():
        cow_id = str(cow.get("cow_id"))
        farm_id = cow.get("farm_id")

        allowed_bulls = allowed_map.get(cow_id)
        if not allowed_bulls:
            continue

        b = bull_feat.copy()
        # if bulls are farm-scoped, keep same farm, else allow all
        if "farm_id" in b.columns and pd.notna(farm_id):
            # tolerate global bulls (farm_id NA)
            b = b[(b["farm_id"].isna()) | (b["farm_id"].astype("string") == str(farm_id))]

        b = b[b["bull_id"].astype(str).isin(list(allowed_bulls))]
        total_candidates += int(len(b))
        if b.empty:
            continue

        b = b.copy()
        b["score"] = _score_bulls_for_cow(cow, b, cfg)
        b = b.sort_values("score", ascending=False)
        b_top = b.head(top_k)

        # merge constraint meta for confidence
        join_cols = ["cow_id", "bull_id"]
        tmp_plans = b_top[["bull_id", "score", "ebv_milk", "ebv_fat", "ebv_protein", "ebv_scc", "price", "available"]].copy()
        tmp_plans["cow_id"] = cow_id
        tmp = _merge_constraints(tmp_plans, constraints)
        tmp = tmp[tmp["allowed"] == True]
        # ensure no forbidden pairs slipped
        forbidden_cnt += int((tmp.get("constraints_reason_code") == "COMMON_ANCESTOR_WITHIN_N").sum())

        for i, r in enumerate(tmp.itertuples(index=False), start=1):
            # convert back to Series-like access
            rr = r._asdict() if hasattr(r, "_asdict") else dict(r)
            bull_id = str(rr.get("bull_id"))
            bull_row = b_top[b_top["bull_id"].astype(str) == bull_id].iloc[0]
            conf = _confidence(pd.Series(rr))
            reasons = _reasons(cow, bull_row)
            rows.append(
                PlanRow(
                    tenant_id=tenant_id,
                    data_version=data_version,
                    mating_plan_run=mating_plan_run,
                    pedigree_run=str(ped_run),
                    farm_id=str(farm_id) if pd.notna(farm_id) else None,
                    cow_id=cow_id,
                    bull_id=bull_id,
                    rank=i,
                    score=float(rr.get("score") or 0.0),
                    confidence=conf,
                    reasons=reasons,
                    constraints_reason_code=str(rr.get("constraints_reason_code") or "OK"),
                    constraints_confidence=str(rr.get("constraints_confidence") or "LOW"),
                )
            )

    out_dir = artifacts_root / data_version / "mating_plan" / mating_plan_run
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame([r.to_dict() for r in rows])
    csv_path = out_dir / "mating_plan.csv"
    df.to_csv(csv_path, index=False)

    xlsx_path = out_dir / "mating_plan.xlsx"
    # wide view for humans
    if not df.empty:
        wide = (
            df.sort_values(["farm_id", "cow_id", "rank"])
            .assign(bull_rank=lambda d: d["bull_id"].astype(str) + " (" + d["confidence"].astype(str) + ")")
        )
        wide_p = wide.pivot_table(
            index=[c for c in ["farm_id", "cow_id"] if c in wide.columns],
            columns="rank",
            values="bull_rank",
            aggfunc="first",
        )
        wide_p.columns = [f"bull_{int(c)}" for c in wide_p.columns]
        wide_p = wide_p.reset_index()
    else:
        wide_p = pd.DataFrame()

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="plan_long", index=False)
        wide_p.to_excel(w, sheet_name="plan", index=False)
        cow_feat.to_excel(w, sheet_name="cows", index=False)
        bull_feat.to_excel(w, sheet_name="bulls", index=False)
        pd.DataFrame(
            [
                {
                    "data_version": data_version,
                    "mating_plan_run": mating_plan_run,
                    "pedigree_run": str(ped_run),
                    "created_at_utc": _utc_ts(),
                    "config": json.dumps(cfg, ensure_ascii=False),
                }
            ]
        ).to_excel(w, sheet_name="meta", index=False)

    summary = {
        "ok": True,
        "tool": "mating_plan_v1",
        "schema": "genomeai.mating_plan.v1",
        "created_at_utc": _utc_ts(),
        "data_version": data_version,
        "mating_plan_run": mating_plan_run,
        "pedigree_run": str(ped_run),
        "inputs": {
            "canonical_dir": str(canonical_dir),
            "constraints_csv": str(constraints_path),
            "cfg_path": str(cfg_path),
        },
        "stats": {
            "cows": int(cows_sel["cow_id"].nunique()),
            "bulls": int(bull_feat["bull_id"].nunique()) if not bull_feat.empty else 0,
            "rows": int(len(df)),
            "avg_candidates_per_cow": float(total_candidates / max(1, int(cows_sel["cow_id"].nunique()))),
            "forbidden_pairs_emitted": int(forbidden_cnt),
        },
        "outputs": {
            "mating_plan_csv": str(csv_path),
            "mating_plan_xlsx": str(xlsx_path),
        },
        "limitations": [
            "v1: простой скоринг и ранжирование; без глобальной оптимизации по стаду.",
            "Качество рекомендаций зависит от полноты EBV/цен/доступности в dm_bulls и продуктивности в dm_lactations.",
        ],
    }
    write_json(out_dir / "summary.json", summary)
    write_checksums(run_root=out_dir, include_subdirs=None)
    return summary


def load_mating_plan(
    *,
    artifacts_root: Path,
    data_version: str,
    mating_plan_run: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """Helper for UI: load long plan CSV."""
    root = Path(artifacts_root) / data_version / "mating_plan"
    run_dir = (root / mating_plan_run) if mating_plan_run else _latest_run_dir(root)
    if not run_dir:
        raise FileNotFoundError("mating_plan run not found")
    csv = run_dir / "mating_plan.csv"
    if not csv.exists():
        raise FileNotFoundError(str(csv))
    return run_dir.name, pd.read_csv(csv)


def is_pair_allowed(
    *,
    artifacts_root: Path,
    data_version: str,
    cow_id: str,
    bull_id: str,
    pedigree_run: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Runtime guard used by UI: checks pair against T6-01 constraints."""
    ped_run, constraints_path = _latest_pedigree_constraints(Path(artifacts_root), data_version)
    if pedigree_run:
        ped_run = str(pedigree_run)
        p = Path(artifacts_root) / data_version / "pedigree" / ped_run / "inbreeding_constraints.csv"
        constraints_path = p if p.exists() else constraints_path
    if not constraints_path:
        return False, {"reason": "constraints_missing"}
    df = pd.read_csv(constraints_path)
    df["cow_id"] = df["cow_id"].astype("string").str.strip()
    df["bull_id"] = df["bull_id"].astype("string").str.strip()
    m = df[(df["cow_id"] == str(cow_id).strip()) & (df["bull_id"] == str(bull_id).strip())]
    if m.empty:
        # if not found, be conservative
        return False, {"reason": "pair_not_found_in_constraints", "pedigree_run": ped_run}
    row = m.iloc[0].to_dict()
    allowed = bool(row.get("allowed"))
    meta = {
        "allowed": allowed,
        "reason_code": row.get("reason_code"),
        "common_ancestors": row.get("common_ancestors"),
        "min_common_depth": row.get("min_common_depth"),
        "confidence": row.get("confidence"),
        "pedigree_run": ped_run,
    }
    return allowed, meta
