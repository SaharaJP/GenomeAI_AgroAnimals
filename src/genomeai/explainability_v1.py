from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        v = float(value)
        return v if np.isfinite(v) else None
    except Exception:
        return None



def _coerce_numeric_series(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        s = values.copy()
    else:
        s = pd.Series(values)
    return pd.to_numeric(s, errors='coerce')


def safe_abs_correlation(x: Any, y: Any) -> float:
    xs = _coerce_numeric_series(x)
    ys = _coerce_numeric_series(y)
    if xs.empty or ys.empty:
        return 0.0
    pair = pd.concat([xs.rename('x'), ys.rename('y')], axis=1).dropna()
    if pair.shape[0] < 2:
        return 0.0
    xvals = pair['x'].to_numpy(dtype=float, copy=False)
    yvals = pair['y'].to_numpy(dtype=float, copy=False)
    x_center = xvals - float(np.mean(xvals))
    y_center = yvals - float(np.mean(yvals))
    x_norm = float(np.sqrt(np.sum(x_center * x_center)))
    y_norm = float(np.sqrt(np.sum(y_center * y_center)))
    if x_norm <= 0.0 or y_norm <= 0.0:
        return 0.0
    corr = float(np.sum(x_center * y_center) / (x_norm * y_norm))
    return abs(corr) if np.isfinite(corr) else 0.0


def _resolve_feature_value(score_df: pd.DataFrame, row: pd.Series, feature: str) -> Optional[float]:
    if row.name in score_df.index and feature in score_df.columns:
        return _safe_float(score_df.loc[row.name, feature])
    return _safe_float(row.get(feature))


def _build_row_input(score_df: pd.DataFrame, row: pd.Series, features: Sequence[str]) -> pd.DataFrame:
    cols = [str(x) for x in features]
    if row.name in score_df.index:
        available = [c for c in cols if c in score_df.columns]
        return score_df.loc[[row.name], available].copy()
    payload = {feature: row.get(feature, pd.NA) for feature in cols}
    return pd.DataFrame([payload], index=[row.name])


def _normalize_rule_name(name: str) -> str:
    s = str(name or '').strip().lower()
    aliases = {
        'higher_bad': 'higher_increases_risk',
        'higher_increases_risk': 'higher_increases_risk',
        'lower_bad': 'lower_increases_risk',
        'lower_increases_risk': 'lower_increases_risk',
        'higher_good': 'higher_increases_prediction',
        'higher_increases_prediction': 'higher_increases_prediction',
        'lower_good': 'lower_increases_prediction',
        'lower_increases_prediction': 'lower_increases_prediction',
        'neutral': 'neutral',
    }
    return aliases.get(s, 'neutral')


def load_explainability_profile(model_dir: Path) -> Dict[str, Any]:
    path = Path(model_dir) / 'explainability_profile.json'
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_explainability_profile(
    *,
    model_dir: Path,
    features: List[str],
    feature_importances: List[float],
    baseline_median: Dict[str, float],
    baseline_scale: Dict[str, float],
    feature_rules: Dict[str, str],
    top_k: int,
    task_kind: str = 'risk',
) -> Dict[str, Any]:
    payload = {
        'schema': 'genomeai.explainability_profile.v1',
        'task_kind': str(task_kind or 'risk'),
        'top_k': int(top_k),
        'features': [str(x) for x in features],
        'feature_importances': {str(f): float(i) for f, i in zip(features, feature_importances)},
        'baseline_median': {str(k): float(v) for k, v in baseline_median.items() if _safe_float(v) is not None},
        'baseline_scale': {str(k): float(v) for k, v in baseline_scale.items() if _safe_float(v) is not None},
        'feature_rules': {str(k): _normalize_rule_name(v) for k, v in (feature_rules or {}).items()},
    }
    path = Path(model_dir) / 'explainability_profile.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


def _risk_direction_sign(rule_name: str) -> float:
    rn = _normalize_rule_name(rule_name)
    if rn == 'higher_increases_risk':
        return 1.0
    if rn == 'lower_increases_risk':
        return -1.0
    return 0.0


def _prediction_direction_sign(rule_name: str) -> float:
    rn = _normalize_rule_name(rule_name)
    if rn == 'higher_increases_prediction':
        return 1.0
    if rn == 'lower_increases_prediction':
        return -1.0
    return 0.0


def _beneficial_step(current: float, baseline: float, rule_name: str, abs_step: float, pct_step: float) -> float:
    sign = _risk_direction_sign(rule_name)
    if sign == 0.0:
        return current
    magnitude = max(abs(abs_step), abs(current) * max(0.0, pct_step), abs(baseline - current) * 0.5)
    if magnitude <= 0:
        magnitude = max(abs(current) * 0.1, 1.0)
    if sign > 0:
        return current - magnitude
    return current + magnitude


def _improve_prediction_step(current: float, baseline: float, rule_name: str, abs_step: float, pct_step: float) -> float:
    sign = _prediction_direction_sign(rule_name)
    if sign == 0.0:
        return current
    magnitude = max(abs(abs_step), abs(current) * max(0.0, pct_step), abs(baseline - current) * 0.5)
    if magnitude <= 0:
        magnitude = max(abs(current) * 0.1, 1.0)
    if sign > 0:
        return current + magnitude
    return current - magnitude


def explain_row(
    *,
    row: pd.Series,
    score_df: pd.DataFrame,
    pipe: Any,
    profile: Dict[str, Any],
    cfg: Dict[str, Any],
    top_k: Optional[int] = None,
) -> Dict[str, Any]:
    features = [str(x) for x in profile.get('features') or [] if str(x) in score_df.columns]
    importances = profile.get('feature_importances') or {}
    medians = profile.get('baseline_median') or {}
    scales = profile.get('baseline_scale') or {}
    rules = profile.get('feature_rules') or {}
    max_k = int(top_k or profile.get('top_k') or ((cfg.get('explainability') or {}).get('top_k') or 3))

    contrib_rows: List[Dict[str, Any]] = []
    for feature in features:
        current = _resolve_feature_value(score_df, row, feature)
        imp = _safe_float(importances.get(feature)) or 0.0
        baseline = _safe_float(medians.get(feature))
        scale = _safe_float(scales.get(feature)) or 1.0
        if current is None or baseline is None or imp <= 0:
            continue
        sign = _risk_direction_sign(str(rules.get(feature) or 'neutral'))
        if sign == 0.0:
            continue
        delta = (current - baseline) / max(abs(scale), 1e-6)
        contribution = float(imp * delta * sign)
        direction = 'risk_up' if contribution >= 0 else 'risk_down'
        contrib_rows.append({
            'feature': feature,
            'current_value': current,
            'baseline_value': baseline,
            'normalized_delta': float(delta),
            'importance_weight': float(imp),
            'direction': direction,
            'contribution_score': contribution,
            'rule': _normalize_rule_name(str(rules.get(feature) or 'neutral')),
        })

    contrib_rows = sorted(contrib_rows, key=lambda x: abs(float(x.get('contribution_score') or 0.0)), reverse=True)
    top_factors = contrib_rows[:max_k]

    current_input = _build_row_input(score_df, row, features)
    try:
        base_proba = float(pipe.predict_proba(current_input)[0, 1])
    except Exception:
        base_proba = _safe_float(row.get('risk_proba')) or 0.0

    cf_rows: List[Dict[str, Any]] = []
    cf_cfg = (cfg.get('explainability') or {}).get('counterfactual', {}) if isinstance(cfg, dict) else {}
    abs_step_default = float(cf_cfg.get('abs_step_default', 1.0))
    pct_step_default = float(cf_cfg.get('pct_step_default', 0.1))
    max_counterfactuals = int(cf_cfg.get('max_counterfactuals', 2))
    for item in top_factors:
        if len(cf_rows) >= max_counterfactuals:
            break
        feature = str(item['feature'])
        current = _resolve_feature_value(score_df, row, feature)
        baseline = _safe_float(medians.get(feature))
        if current is None or baseline is None:
            continue
        step_abs = float(((cf_cfg.get('feature_steps') or {}).get(feature) or abs_step_default))
        candidate = _beneficial_step(current, baseline, str(item.get('rule') or 'neutral'), step_abs, pct_step_default)
        changed = current_input.copy()
        changed.loc[row.name, feature] = candidate
        try:
            new_proba = float(pipe.predict_proba(changed)[0, 1])
        except Exception:
            continue
        delta = float(new_proba - base_proba)
        if delta == 0:
            continue
        cf_rows.append({
            'feature': feature,
            'current_value': current,
            'suggested_value': float(candidate),
            'risk_proba_before': base_proba,
            'risk_proba_after': new_proba,
            'risk_delta': delta,
        })
    cf_rows = sorted(cf_rows, key=lambda x: x['risk_delta'])

    display_factors = []
    for item in top_factors:
        sign_text = '↑ риск' if float(item.get('contribution_score') or 0.0) >= 0 else '↓ риск'
        display_factors.append(f"{item['feature']}={item['current_value']:.3f} ({sign_text}, baseline={item['baseline_value']:.3f})")

    display_cfs = []
    for item in cf_rows:
        display_cfs.append(
            f"если {item['feature']} изменить с {item['current_value']:.3f} до {item['suggested_value']:.3f}, риск может измениться на {item['risk_delta']:.4f}"
        )

    return {
        'top_factors': top_factors,
        'counterfactuals': cf_rows,
        'top_factors_text': '; '.join(display_factors) if display_factors else 'insufficient_explainability_data',
        'counterfactuals_text': '; '.join(display_cfs) if display_cfs else 'no_simple_counterfactual',
        'base_proba': base_proba,
    }


def aggregate_native_feature_importances(pipe: Any, features: Sequence[str]) -> Dict[str, float]:
    feature_list = [str(x) for x in features]
    out = {f: 0.0 for f in feature_list}
    try:
        model = pipe.named_steps.get('model')
        pre = pipe.named_steps.get('pre')
        raw_importances = getattr(model, 'feature_importances_', None)
        if raw_importances is not None and pre is not None:
            names = list(pre.get_feature_names_out())
            for name, imp in zip(names, list(raw_importances)):
                val = _safe_float(imp) or 0.0
                base = str(name).split('__', 1)[1] if '__' in str(name) else str(name)
                matched = None
                for f in feature_list:
                    if base == f or base.startswith(f + '_'):
                        matched = f
                        break
                if matched is not None:
                    out[matched] = out.get(matched, 0.0) + float(val)
    except Exception:
        pass
    return out


def infer_prediction_rules_from_sensitivity(
    *,
    pipe: Any,
    numeric_features: Sequence[str],
    baseline_median: Dict[str, float],
    baseline_scale: Dict[str, float],
    abs_step_default: float = 1.0,
) -> Dict[str, str]:
    features = [str(x) for x in numeric_features]
    if not features:
        return {}
    baseline_row = {f: baseline_median.get(f) for f in features}
    base_df = pd.DataFrame([baseline_row])
    try:
        base_pred = float(pipe.predict(base_df)[0])
    except Exception:
        base_pred = 0.0
    out: Dict[str, str] = {}
    for feature in features:
        current = _safe_float(baseline_median.get(feature)) or 0.0
        step = max(abs(_safe_float(baseline_scale.get(feature)) or 0.0), float(abs_step_default), abs(current) * 0.1, 1.0)
        up_df = base_df.copy()
        down_df = base_df.copy()
        up_df.loc[0, feature] = current + step
        down_df.loc[0, feature] = current - step
        try:
            up_pred = float(pipe.predict(up_df)[0])
            down_pred = float(pipe.predict(down_df)[0])
        except Exception:
            out[feature] = 'neutral'
            continue
        if abs(up_pred - base_pred) < 1e-9 and abs(down_pred - base_pred) < 1e-9:
            out[feature] = 'neutral'
        elif up_pred >= down_pred:
            out[feature] = 'higher_increases_prediction'
        else:
            out[feature] = 'lower_increases_prediction'
    return out


def explain_regression_row(
    *,
    row: pd.Series,
    score_df: pd.DataFrame,
    pipe: Any,
    profile: Dict[str, Any],
    cfg: Dict[str, Any],
    top_k: Optional[int] = None,
) -> Dict[str, Any]:
    features = [str(x) for x in profile.get('features') or [] if str(x) in score_df.columns]
    importances = profile.get('feature_importances') or {}
    medians = profile.get('baseline_median') or {}
    scales = profile.get('baseline_scale') or {}
    rules = profile.get('feature_rules') or {}
    explain_cfg = (cfg.get('productivity_explainability') or cfg.get('explainability') or {}) if isinstance(cfg, dict) else {}
    max_k = int(top_k or profile.get('top_k') or explain_cfg.get('top_k') or 3)

    contrib_rows: List[Dict[str, Any]] = []
    for feature in features:
        current = _resolve_feature_value(score_df, row, feature)
        imp = _safe_float(importances.get(feature)) or 0.0
        baseline = _safe_float(medians.get(feature))
        scale = _safe_float(scales.get(feature)) or 1.0
        if current is None or baseline is None:
            continue
        if imp <= 0:
            imp = 0.01
        sign = _prediction_direction_sign(str(rules.get(feature) or 'neutral'))
        if sign == 0.0:
            sign = 1.0 if current >= baseline else -1.0
        delta = (current - baseline) / max(abs(scale), 1e-6)
        contribution = float(imp * delta * sign)
        direction = 'prediction_up' if contribution >= 0 else 'prediction_down'
        contrib_rows.append({
            'feature': feature,
            'current_value': current,
            'baseline_value': baseline,
            'normalized_delta': float(delta),
            'importance_weight': float(imp),
            'direction': direction,
            'contribution_score': contribution,
            'rule': _normalize_rule_name(str(rules.get(feature) or 'neutral')),
        })
    contrib_rows = sorted(contrib_rows, key=lambda x: abs(float(x.get('contribution_score') or 0.0)), reverse=True)
    top_factors = contrib_rows[:max_k]

    current_input = _build_row_input(score_df, row, features)
    try:
        base_pred = float(pipe.predict(current_input)[0])
    except Exception:
        base_pred = _safe_float(row.get('y_pred')) or 0.0

    cf_cfg = explain_cfg.get('counterfactual', {}) if isinstance(explain_cfg, dict) else {}
    abs_step_default = float(cf_cfg.get('abs_step_default', 1.0))
    pct_step_default = float(cf_cfg.get('pct_step_default', 0.1))
    max_counterfactuals = int(cf_cfg.get('max_counterfactuals', 2))
    feature_steps = cf_cfg.get('feature_steps') or {}
    cf_rows: List[Dict[str, Any]] = []
    for item in top_factors:
        if len(cf_rows) >= max_counterfactuals:
            break
        feature = str(item['feature'])
        current = _resolve_feature_value(score_df, row, feature)
        baseline = _safe_float(medians.get(feature))
        if current is None or baseline is None:
            continue
        step_abs = float(feature_steps.get(feature) or abs_step_default)
        candidate = _improve_prediction_step(current, baseline, str(item.get('rule') or 'neutral'), step_abs, pct_step_default)
        changed = current_input.copy()
        changed.loc[row.name, feature] = candidate
        try:
            new_pred = float(pipe.predict(changed)[0])
        except Exception:
            continue
        delta = float(new_pred - base_pred)
        if abs(delta) < 1e-9:
            continue
        cf_rows.append({
            'feature': feature,
            'current_value': current,
            'suggested_value': float(candidate),
            'prediction_before': base_pred,
            'prediction_after': new_pred,
            'prediction_delta': delta,
        })
    cf_rows = sorted(cf_rows, key=lambda x: x['prediction_delta'], reverse=True)

    display_factors = []
    for item in top_factors:
        sign_text = '↑ прогноз' if float(item.get('contribution_score') or 0.0) >= 0 else '↓ прогноз'
        display_factors.append(f"{item['feature']}={item['current_value']:.3f} ({sign_text}, baseline={item['baseline_value']:.3f})")
    display_cfs = []
    for item in cf_rows:
        display_cfs.append(
            f"если {item['feature']} изменить с {item['current_value']:.3f} до {item['suggested_value']:.3f}, прогноз продуктивности может измениться на {item['prediction_delta']:.2f} кг"
        )

    return {
        'top_factors': top_factors,
        'counterfactuals': cf_rows,
        'top_factors_text': '; '.join(display_factors) if display_factors else 'insufficient_explainability_data',
        'counterfactuals_text': '; '.join(display_cfs) if display_cfs else 'no_simple_counterfactual',
        'base_prediction': base_pred,
    }
