from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def _sanitize_llm_numbers(text: str, fact_pack_str: str) -> str:
    """Pragmatic guardrail: remove numbers not present in fact_pack."""

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok in fact_pack_str:
            return tok
        return "n/a"

    return re.sub(r"\b\d+(?:\.\d+)?\b", repl, text)


def generate_regular_report_text_fallback(fact_pack: Dict[str, Any], *, audience: str) -> Dict[str, str]:
    """Deterministic regular-report narrative without LLM."""
    v = fact_pack.get("versions", {}) or {}
    mods = fact_pack.get("modules", {}) or {}

    kpi = (mods.get("kpi") or {})
    repro = (mods.get("repro") or {})
    econ = (mods.get("economics") or {})
    mast = ((mods.get("health") or {}).get("mastitis_risk") or {})
    alerts = (mods.get("alerts_v2") or {})
    pbs = (mods.get("playbooks") or {})

    exec_lines: List[str] = [
        f"Связка версий: data_version={v.get('data_version')}, model_version={v.get('model_version')}, report_version={{REPORT_VERSION}}",
        f"Период: {fact_pack.get('period')} | asof_date={fact_pack.get('asof_date')}",
        fact_pack.get("disclaimer", ""),
        "",
    ]

    if kpi.get("available"):
        exec_lines.append(
            f"KPI: kpi_count={kpi.get('kpi_count','NA')}, alerts={kpi.get('alert_count','NA')} (источник: {kpi.get('sources',{}).get('kpi_summary','NA')})"
        )
    else:
        exec_lines.append("KPI: NA (нет артефактов)")

    exec_lines.append(f"Alert Center v2: count={alerts.get('count','NA')} (детерминированные правила)")

    prod_explain = fact_pack.get("productivity_explainability", {}) or {}
    if prod_explain.get("available"):
        explain = prod_explain.get("explainability") or {}
        if explain.get("available"):
            tf_counts = explain.get("top_feature_counts") or {}
            if tf_counts:
                exec_lines.append("Explainability продуктивности: частые top-факторы = " + json.dumps(tf_counts, ensure_ascii=False))

    rec_lines: List[str] = []

    if prod_explain.get("available"):
        rows = prod_explain.get("animal_explainability") or []
        if rows:
            rec_lines.append("\nExplainability продуктивности — почему животные попали в ранжирование:")
            for r in rows[:10]:
                line = f"- animal_id={r.get('animal_id','NA')} pred={r.get('prediction','NA')} confidence={r.get('confidence','NA')} action={r.get('action','NA')}"
                tf = str(r.get('explain_top_factors_text') or '').strip()
                cf = str(r.get('explain_counterfactuals_text') or '').strip()
                if tf and tf != 'insufficient_explainability_data':
                    line += f" | why={tf}"
                if cf and cf != 'no_simple_counterfactual':
                    line += f" | counterfactual={cf}"
                rec_lines.append(line)

    if mast.get("available"):
        exec_lines.append(
            f"Риск мастита: horizon_days={mast.get('horizon_days','NA')}, threshold={mast.get('risk_threshold','NA')}"
        )
        explain = mast.get("explainability") or {}
        if explain.get("available"):
            tf_counts = explain.get("top_feature_counts") or {}
            if tf_counts:
                exec_lines.append("Explainability: частые top-факторы = " + json.dumps(tf_counts, ensure_ascii=False))
    else:
        exec_lines.append("Риск мастита: NA")

    if repro.get("available"):
        wl = repro.get("worklists_counts", {}) or {}
        exec_lines.append(f"Воспроизводство: worklists={json.dumps(wl, ensure_ascii=False)}")
    else:
        exec_lines.append("Воспроизводство: NA")

    if econ.get("available"):
        exec_lines.append(f"Экономика: economics_run={econ.get('economics_run','NA')}")
    else:
        exec_lines.append("Экономика: NA")

    pb_by_type: Dict[str, Dict[str, Any]] = {}
    if isinstance(pbs, dict) and (pbs.get("recommended") or []):
        for p in (pbs.get("recommended") or []):
            try:
                if str(p.get("target_kind") or "") == "alert":
                    pb_by_type[str(p.get("target_type") or "").strip()] = p
            except Exception:
                continue
    top_alerts = alerts.get("top") or []
    if top_alerts:
        rec_lines.append("ТОП алерты (до 10):")
        for a in top_alerts[:10]:
            at = str(a.get("alert_type") or "").strip()
            ent = str(a.get("object_id") or a.get("entity_id") or "NA")
            why = a.get("why")
            why_s = json.dumps(why, ensure_ascii=False)[:400] if isinstance(why, dict) else str(why or "NA")
            line = f"- [{a.get('severity','NA')}] {a.get('title','NA')} | type={at or 'NA'} | object={a.get('object_type','NA')}:{ent} | why={why_s}"
            pb = pb_by_type.get(at)
            if pb:
                line += f" | playbook={pb.get('name','NA')} (version_id={pb.get('version_id','NA')})"
            rec_lines.append(line)

            if pb:
                steps = list(pb.get("steps") or [])
                for i, st in enumerate(steps[:3], start=1):
                    title = str(st.get("title") or st.get("key") or "step")
                    rec_lines.append(f"  {i}. {title}")
    else:
        rec_lines.append("Алерты: NA")

    if mast.get("available"):
        top = mast.get("top_risk") or []
        if top:
            rec_lines.append("\nРиск мастита — рекомендованные действия:")
            for r in top[:10]:
                risk_value = r.get('risk', r.get('risk_score', r.get('risk_proba', 'NA')))
                line = f"- animal_id={r.get('animal_id','NA')} risk={risk_value} confidence={r.get('confidence','NA')} action={r.get('recommended_action','NA')}"
                tf = str(r.get('explain_top_factors_text') or '').strip()
                cf = str(r.get('explain_counterfactuals_text') or '').strip()
                if tf and tf != 'insufficient_explainability_data':
                    line += f" | why={tf}"
                if cf and cf != 'no_simple_counterfactual':
                    line += f" | counterfactual={cf}"
                rec_lines.append(line)

    if repro.get("available"):
        rec_lines.append("\nWorklist (воспроизводство) — что сделать:")
        wl_top = repro.get("worklists_top") or []
        for r in wl_top[:10]:
            rec_lines.append(
                f"- [{r.get('worklist_type','NA')}] animal_id={r.get('animal_id','NA')} priority={r.get('priority','NA')} due={r.get('due_date','NA')} reason={r.get('reason','NA')}"
            )

    lim_lines: List[str] = [
        "Ограничения:",
        "- Текст построен строго из fact_pack; отсутствующие значения помечаются как NA.",
        "- Секции появляются только при наличии артефактов соответствующего модуля.",
        "- LLM может быть отключён; в этом случае используется шаблон (fallback).",
    ]

    if str(audience).lower() == "ops":
        lim_lines.append("- Источники по модулям:")
        for name, block in (mods or {}).items():
            if isinstance(block, dict):
                sources = block.get("sources") or {}
                if sources:
                    lim_lines.append(f"  - {name}: {json.dumps(sources, ensure_ascii=False)}")

    return {
        "executive_summary": "\n".join(exec_lines).strip(),
        "recommendations": "\n".join(rec_lines).strip(),
        "limitations": "\n".join(lim_lines).strip(),
    }


def generate_regular_report_text_llm(
    fact_pack: Dict[str, Any],
    *,
    audience: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> Tuple[Dict[str, str], bool, Optional[str]]:
    """Optional LLM narrative strictly grounded on fact_pack."""
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return {}, False, "openai_python_package_not_installed"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}, False, "OPENAI_API_KEY_not_set"

    client = OpenAI(api_key=api_key)
    chosen_model = model or os.getenv("GENOMEAI_OPENAI_MODEL", "gpt-4o-mini")
    fact_pack_str = json.dumps(fact_pack, ensure_ascii=False, indent=2)

    system = (
        "Вы — ассистент по регулярному отчёту в животноводстве. "
        "Вы ДОЛЖНЫ использовать ТОЛЬКО факты из предоставленного JSON fact_pack. "
        "Запрещено придумывать числа/проценты/суммы/датировки. "
        "Если факта нет — пишите 'NA'. "
        "Выведите 3 секции: Executive summary, Recommendations, Limitations. "
        "В Recommendations укажите 'что сделать' (осмотр/проверка/проба/перепроверка данных). "
        "Если в fact_pack есть modules.playbooks.recommended — используйте их как 'рекомендуемый план действий' (кратко, по шагам). "
        "Не используйте формулировки диагнозов."
    )
    user = f"audience={audience}\n\nfact_pack_json:\n{fact_pack_str}"

    try:
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
    except Exception as e:
        return {}, False, f"llm_error:{type(e).__name__}"

    text = _sanitize_llm_numbers(text, fact_pack_str)

    sections = {"executive_summary": "", "recommendations": "", "limitations": ""}
    cur = None
    for line in text.splitlines():
        l = line.strip()
        low = l.lower()
        if "executive" in low and "summary" in low:
            cur = "executive_summary"
            continue
        if "recommend" in low:
            cur = "recommendations"
            continue
        if "limit" in low:
            cur = "limitations"
            continue
        if cur:
            sections[cur] += (line + "\n")

    if not any(sections.values()):
        sections["executive_summary"] = text
    sections = {k: v.strip() for k, v in sections.items()}
    return sections, True, None


def render_regular_report_markdown(
    *,
    narrative: Dict[str, str],
    fact_pack: Dict[str, Any],
    out_path: Path,
    report_version: str,
    audience: str,
    llm_used: bool,
) -> None:
    v = fact_pack.get("versions", {}) or {}
    lines: List[str] = []
    lines.append(f"# GenomeAI AgroAnimals — Регулярный отчёт ({audience})")
    lines.append("")
    lines.append(f"**report_version:** {report_version}")
    lines.append(f"**created_at_utc:** {fact_pack.get('created_at_utc')}")
    lines.append(f"**data_version:** {v.get('data_version','NA')}")
    lines.append(f"**model_version:** {v.get('model_version','NA')}")
    lines.append(f"**period:** {fact_pack.get('period','NA')} | **asof_date:** {fact_pack.get('asof_date','NA')}")
    lines.append(f"**mode:** {'LLM' if llm_used else 'Fallback'}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive summary")
    lines.append(narrative.get("executive_summary", "NA") or "NA")
    lines.append("")
    lines.append("## Recommendations")
    lines.append(narrative.get("recommendations", "NA") or "NA")
    lines.append("")
    lines.append("## Limitations")
    lines.append(narrative.get("limitations", "NA") or "NA")
    lines.append("")

    if str(audience).lower() == "ops":
        mods = fact_pack.get("modules", {}) or {}
        lines.append("---")
        lines.append("## Appendices")
        for mod_name, block in mods.items():
            lines.append("")
            lines.append(f"### {mod_name}")
            if not isinstance(block, dict) or not block.get("available", True):
                lines.append("NA")
                continue
            for key in ["kpi_wide_top", "kpi_alerts_top", "kpis_top", "worklists_top", "top_pairs", "summary_farm_top", "top", "top_risk"]:
                rows = block.get(key)
                if isinstance(rows, list) and rows:
                    df = pd.DataFrame(rows)
                    lines.append("")
                    lines.append(f"**{key}**")
                    lines.append(df.to_markdown(index=False))
            explain = block.get("explainability") or {}
            if isinstance(explain, dict) and explain.get("available"):
                lines.append("")
                lines.append("**explainability**")
                lines.append("```json")
                lines.append(json.dumps(explain, ensure_ascii=False, indent=2))
                lines.append("```")
            src = block.get("sources") or {}
            if src:
                lines.append("")
                lines.append("**sources**")
                lines.append("```json")
                lines.append(json.dumps(src, ensure_ascii=False, indent=2))
                lines.append("```")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = [
    "generate_regular_report_text_fallback",
    "generate_regular_report_text_llm",
    "render_regular_report_markdown",
]
