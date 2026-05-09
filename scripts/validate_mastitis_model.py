"""
Эмпирическая валидация ML-модели скрининга маститов и impact analysis
для платформы GenomeAI AgroAnimals.

Соответствует разделу 3.2.3 ВКР: логистическая регрессия по 8 признакам.

Данные:
- milk_yields.enhanced.json (37310 ежедневных наблюдений, 350 коров, ~6 мес.)
- dm_health_events.csv (37 событий мастита, 21 хромоты, 3 кетоза)
- dm_lactations.csv (calving_date, lactation_no)

Метрики:
- ROC-AUC, Precision@k, Recall с 95% bootstrap-CI (1000 итераций, seed=42)
- Сравнение с тривиальным baseline: rule "SCC > 400k" (порог из табл. 1.1.1)

Impact analysis:
- t-критерий Уэлча на 5 событиях мастита (Malina x2, Zvezdochka, etc.)
- Окно ±14 дней, тестируем H0: E[milk_pre] = E[milk_post]
"""

import json
import csv
import math
import random
from datetime import date, timedelta
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score,
    precision_score,
    recall_score,
    confusion_matrix,
)
from scipy import stats

ROOT = Path("/tmp/thesis_validation")
SEED = 42
np.random.seed(SEED)
random.seed(SEED)

PRED_HORIZON_DAYS = 14  # τ из формулировки в дипломе


def load_data():
    yields = json.load(open(ROOT / "milk_yields.enhanced.json"))
    df_y = pd.DataFrame(yields)
    df_y["date"] = pd.to_datetime(df_y["date"]).dt.date
    df_y["animal_id"] = df_y["animal_id"].astype(str)

    events = pd.read_csv(ROOT / "dm_health_events.csv")
    events["event_date"] = pd.to_datetime(events["event_date"]).dt.date
    events["animal_id"] = events["animal_id"].astype(str)
    mastitis = events[events["event_type"] == "mastitis"].copy()

    lact = pd.read_csv(ROOT / "dm_lactations.csv")
    lact["animal_id"] = lact["animal_id"].astype(str)
    lact["calving_date"] = pd.to_datetime(lact["calving_date"]).dt.date

    return df_y, mastitis, lact


def build_features(df_y, mastitis, lact):
    """Для каждой пары (cow, date) собрать вектор признаков x_1...x_8 и метку y."""
    df_y = df_y.sort_values(["animal_id", "date"]).reset_index(drop=True)

    # ΔSCC и rolling features через groupby
    df_y["scc_avg14"] = df_y.groupby("animal_id")["scc_cells_ml"].transform(
        lambda s: s.rolling(window=14, min_periods=3).mean().shift(1)
    )
    df_y["delta_scc"] = df_y["scc_cells_ml"] - df_y["scc_avg14"]
    df_y["milk_avg3"] = df_y.groupby("animal_id")["milk_kg"].transform(
        lambda s: s.rolling(window=3, min_periods=1).mean()
    )
    df_y["milk_avg10"] = df_y.groupby("animal_id")["milk_kg"].transform(
        lambda s: s.rolling(window=10, min_periods=3).mean().shift(3)
    )
    df_y["milk_drop_3d_pct"] = (
        (df_y["milk_avg10"] - df_y["milk_avg3"]) / df_y["milk_avg10"]
    ).clip(-1, 1)

    # x_4: DIM (день лактации) = date - calving_date
    cal = lact.set_index("animal_id")["calving_date"].to_dict()
    lact_no = lact.set_index("animal_id")["lactation_no"].to_dict()

    def dim(row):
        cd = cal.get(row["animal_id"])
        return (row["date"] - cd).days if cd else 100

    df_y["dim"] = df_y.apply(dim, axis=1)
    df_y["lactation_no"] = df_y["animal_id"].map(lact_no).fillna(2).astype(int)

    # x_7: days since last mastitis (большое значение если не было)
    # Для каждого (cow, date) — найти последний мастит до date
    last_mast = defaultdict(list)
    for _, r in mastitis.iterrows():
        last_mast[r["animal_id"]].append(r["event_date"])

    def days_since_last_mast(row):
        events = last_mast.get(row["animal_id"], [])
        prev = [e for e in events if e < row["date"]]
        return (row["date"] - max(prev)).days if prev else 9999

    df_y["days_since_mast"] = df_y.apply(days_since_last_mast, axis=1)

    # x_8: квартал
    df_y["quarter"] = pd.DatetimeIndex(df_y["date"]).quarter.astype(int)

    # Target: будет ли клинический мастит в окне (t, t+τ]?
    fut_mast = defaultdict(list)
    for _, r in mastitis.iterrows():
        fut_mast[r["animal_id"]].append(r["event_date"])

    def label(row):
        events = fut_mast.get(row["animal_id"], [])
        for e in events:
            d = (e - row["date"]).days
            if 1 <= d <= PRED_HORIZON_DAYS:
                return 1
        return 0

    df_y["y"] = df_y.apply(label, axis=1)

    # Удалить наблюдения внутри активного эпизода (от события до +14 дней)
    # — чтобы не учить модель на "пик SCC во время мастита предсказывает мастит"
    in_event = []
    for _, r in df_y.iterrows():
        events = last_mast.get(r["animal_id"], []) + fut_mast.get(r["animal_id"], [])
        # Если date в окне [event, event+RECOVERY_DAYS] — это активный эпизод
        active = any(0 <= (r["date"] - e).days <= 14 for e in events if e <= r["date"])
        in_event.append(active)
    df_y["in_event"] = in_event

    # Финальный фрейм: только годные наблюдения с заполненными rolling-features
    df = df_y.dropna(subset=["scc_avg14", "milk_avg10", "delta_scc"]).copy()
    df = df[~df["in_event"]].copy()  # исключить активные эпизоды
    df["dim"] = df["dim"].clip(lower=1, upper=500)
    return df


def evaluate_with_ci(y_true, y_score, n_boot=1000, seed=SEED):
    """Bootstrap 95% CI для ROC-AUC."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    auc_main = roc_auc_score(y_true, y_score)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y_true[idx], y_score[idx]))
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    return auc_main, lo, hi


def precision_recall_at_threshold(y_true, y_prob, threshold=0.5):
    y_pred = (y_prob >= threshold).astype(int)
    if y_pred.sum() == 0:
        return 0.0, 0.0, 0
    p = precision_score(y_true, y_pred, zero_division=0)
    r = recall_score(y_true, y_pred, zero_division=0)
    return p, r, int(y_pred.sum())


def split_train_test_by_cow(df, test_fraction=0.3, seed=SEED):
    """Cow-level split: исключаем data leak (одна корова — либо в train, либо в test)."""
    rng = np.random.default_rng(seed)
    cows = df["animal_id"].unique()
    rng.shuffle(cows)
    n_test = int(len(cows) * test_fraction)
    test_cows = set(cows[:n_test])
    train = df[~df["animal_id"].isin(test_cows)]
    test = df[df["animal_id"].isin(test_cows)]
    return train, test


def main():
    print("=== Loading data ===")
    df_y, mastitis, lact = load_data()
    print(f"  daily records: {len(df_y)}, animals: {df_y['animal_id'].nunique()}")
    print(f"  mastitis events: {len(mastitis)}")

    print("\n=== Feature engineering ===")
    df = build_features(df_y, mastitis, lact)
    print(f"  feature rows: {len(df)}, positive labels: {df['y'].sum()} ({100*df['y'].mean():.2f}%)")

    feat_cols = [
        "scc_cells_ml",   # x1
        "milk_avg3",      # x2
        "delta_scc",      # x3
        "dim",            # x4
        "lactation_no",   # x5
        "milk_drop_3d_pct",  # x6
        "days_since_mast",   # x7
        "quarter",           # x8
    ]

    print("\n=== Train/test split (cow-level) ===")
    train, test = split_train_test_by_cow(df, test_fraction=0.3)
    print(f"  train: {len(train)} rows ({train['animal_id'].nunique()} cows), "
          f"test: {len(test)} rows ({test['animal_id'].nunique()} cows)")
    print(f"  positives train: {int(train['y'].sum())}, test: {int(test['y'].sum())}")

    Xtr, ytr = train[feat_cols].values, train["y"].values
    Xte, yte = test[feat_cols].values, test["y"].values

    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)
    Xte_s = scaler.transform(Xte)

    print("\n=== Train logistic regression (L2, 5-fold CV-tuned C) ===")
    # 5-fold CV для подбора C (обратное к λ)
    from sklearn.model_selection import GridSearchCV
    grid = GridSearchCV(
        LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED),
        {"C": [0.01, 0.1, 1.0, 10.0]},
        cv=5,
        scoring="roc_auc",
        n_jobs=1,
    )
    grid.fit(Xtr_s, ytr)
    best_C = grid.best_params_["C"]
    print(f"  best C = {best_C} (CV ROC-AUC: {grid.best_score_:.4f})")

    model = grid.best_estimator_
    y_prob = model.predict_proba(Xte_s)[:, 1]

    print("\n=== Test metrics (logistic regression) ===")
    auc, lo, hi = evaluate_with_ci(yte, y_prob, n_boot=1000)
    print(f"  ROC-AUC: {auc:.3f} (95% CI [{lo:.3f}, {hi:.3f}])")
    for thr in [0.3, 0.5, 0.6, 0.7]:
        p, r, n = precision_recall_at_threshold(yte, y_prob, thr)
        print(f"  Threshold {thr}: Precision = {p:.3f}, Recall = {r:.3f}, predicted-positives = {n}")

    # Также: по диплому P_thresh = 0.6 целевой; найдём best operating point по F1
    from sklearn.metrics import f1_score
    f1s = []
    for thr in np.linspace(0.05, 0.95, 19):
        y_pred = (y_prob >= thr).astype(int)
        f1s.append((thr, f1_score(yte, y_pred, zero_division=0)))
    best_thr, best_f1 = max(f1s, key=lambda x: x[1])
    p, r, _ = precision_recall_at_threshold(yte, y_prob, best_thr)
    print(f"  Best F1 threshold: {best_thr:.2f}, F1 = {best_f1:.3f}, P = {p:.3f}, R = {r:.3f}")

    print("\n=== Baseline 1: rule SCC > 400k ===")
    base_pred1 = (test["scc_cells_ml"] >= 400_000).astype(int).values
    auc_b1 = roc_auc_score(yte, test["scc_cells_ml"].values)
    p1 = precision_score(yte, base_pred1, zero_division=0)
    r1 = recall_score(yte, base_pred1, zero_division=0)
    print(f"  ROC-AUC (SCC alone): {auc_b1:.3f}")
    print(f"  rule SCC>400k: Precision = {p1:.3f}, Recall = {r1:.3f}, predicted = {base_pred1.sum()}")

    print("\n=== Baseline 2: trivial (random by class prevalence) ===")
    rng = np.random.default_rng(SEED)
    prev = ytr.mean()
    y_rand = rng.random(len(yte))
    base_pred2 = (y_rand < prev).astype(int)
    p2 = precision_score(yte, base_pred2, zero_division=0)
    r2 = recall_score(yte, base_pred2, zero_division=0)
    auc_b2 = roc_auc_score(yte, y_rand)
    print(f"  Random ROC-AUC: {auc_b2:.3f}, P = {p2:.3f}, R = {r2:.3f}")

    print("\n=== Confusion matrix at threshold {} ===".format(round(best_thr, 2)))
    y_pred = (y_prob >= best_thr).astype(int)
    cm = confusion_matrix(yte, y_pred)
    print(f"  TN = {cm[0,0]}, FP = {cm[0,1]}")
    print(f"  FN = {cm[1,0]}, TP = {cm[1,1]}")

    print("\n=== Feature importances (model.coef_, scaled) ===")
    coefs = model.coef_[0]
    for name, c in sorted(zip(feat_cols, coefs), key=lambda x: -abs(x[1])):
        print(f"  {name:22s}: {c:+.4f}")

    # === IMPACT ANALYSIS на 5 событиях мастита ===
    # P3-1: K(t)=T+S+E+ε decomposition before Welch (thesis §3.2.2, formula 3.8)
    from web_cabinet.ai.impact_decomposition import decompose_for_welch
    print("\n=== Impact analysis (Welch t-test on T+S-detrended residuals, 14d windows) ===")
    print("    Event ID         | cow  | date       | dM_adj (kg) | t      | p-value | sig?")
    print("    -----------------+------+------------+-------------+--------+---------+------")
    chosen = mastitis.head(5)
    impact_results = []
    for _, ev in chosen.iterrows():
        cow = ev["animal_id"]
        ed = ev["event_date"]
        cow_data = df_y[df_y["animal_id"] == cow].copy().sort_values("date")
        # Use the full per-cow series so estimate_trend has data outside the event window
        if len(cow_data) < 30:
            continue
        values = cow_data["milk_kg"].values
        dates_list = list(cow_data["date"])
        pre, post = decompose_for_welch(
            values, dates_list, ed, window_days=14,
        )
        if len(pre) < 3 or len(post) < 3:
            continue
        t, pval = stats.ttest_ind(pre, post, equal_var=False)
        delta = float(post.mean() - pre.mean())
        sig = "**" if pval < 0.05 else "n/s"
        ev_short = ev["event_id"][:14]
        print(f"    {ev_short:16s} | {cow:4s} | {ed} | {delta:+.2f}      | {t:+.3f} | {pval:.4f}  | {sig}")
        impact_results.append({
            "event_id": ev["event_id"],
            "cow": cow, "event_date": str(ed),
            "delta_milk_adj": round(float(delta), 2),
            "t_stat": round(float(t), 3),
            "p_value": round(float(pval), 4),
            "significant_at_005": bool(pval < 0.05),
            "n_pre": len(pre), "n_post": len(post),
            "method": "decomposed_welch_t",
        })

    # Сохранить результаты для LaTeX
    out = {
        "model": {
            "type": "LogisticRegression",
            "regularization": "L2",
            "best_C": float(best_C),
            "cv_folds": 5,
            "class_weight": "balanced",
            "seed": SEED,
            "horizon_days": PRED_HORIZON_DAYS,
        },
        "data": {
            "feature_rows": len(df),
            "positive_labels": int(df["y"].sum()),
            "positive_rate": round(float(df["y"].mean()), 4),
            "train_rows": len(train),
            "test_rows": len(test),
            "n_train_cows": int(train['animal_id'].nunique()),
            "n_test_cows": int(test['animal_id'].nunique()),
        },
        "metrics_lr": {
            "roc_auc": round(float(auc), 3),
            "roc_auc_ci_lo": round(float(lo), 3),
            "roc_auc_ci_hi": round(float(hi), 3),
            "best_f1_threshold": round(float(best_thr), 2),
            "best_f1": round(float(best_f1), 3),
            "best_f1_precision": round(float(p), 3),
            "best_f1_recall": round(float(r), 3),
        },
        "metrics_baseline_scc_400k": {
            "roc_auc": round(float(auc_b1), 3),
            "precision": round(float(p1), 3),
            "recall": round(float(r1), 3),
            "predicted_positives": int(base_pred1.sum()),
        },
        "metrics_baseline_random": {
            "roc_auc": round(float(auc_b2), 3),
            "precision": round(float(p2), 3),
            "recall": round(float(r2), 3),
        },
        "feature_importances": {n: round(float(c), 4) for n, c in zip(feat_cols, coefs)},
        "impact_analysis": impact_results,
    }
    with open(ROOT / "validation_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {ROOT / 'validation_results.json'}")


if __name__ == "__main__":
    main()
