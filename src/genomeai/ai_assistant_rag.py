from __future__ import annotations

"""T8-02: AI‑ассистент “только по данным системы” (RAG + guardrails).

Это модуль *offline-core*.

Ключевые принципы (обязательные):
1) Ответы ТОЛЬКО по данным/витринам/алертам/decision log/отчётам системы.
2) Всегда указывать источники и версии (data_version/model_version/report_version).
3) Запрещено придумывать цифры/события; при отсутствии — писать NA.
4) Любые рекомендации — только decision-support и должны ссылаться на факты.
5) Есть fallback без LLM.

Текущая реализация (v1):
- knowledge sources: fact_pack (из T8-01), decision_log.csv (legacy) и decision_log_v2 (если доступен в web.db),
  последние регулярные отчёты (MD, если есть).
- retrieval: TF‑IDF поверх текстовых "чанков" fact_pack/логов.
- guardrails: простые, но строгие правила отказа + обязательные цитаты.

Артефакты (минимально):
- В UI лог запросов/ответов пишется в web.db (таблица assistant_log_v1) через genomeai.assistant_log.
"""

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .regular_reports import build_fact_pack_regular
from .playbooks import list_active_playbooks
from .feedback_loop import DEFAULT_CFG_PATH as FEEDBACK_CFG_PATH, compute_feedback_metrics as core_compute_feedback_metrics, load_feedback_config
from .versioning import write_json
from .copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack
from .copilot_target_resolver import build_copilot_web_target
from .copilot_tools import execute_copilot_tool, load_copilot_tools_config, plan_copilot_tools
from .copilot_weekly_plan import build_weekly_plan_from_fact_pack, is_weekly_plan_request, load_weekly_plan_copilot_config, render_weekly_plan_answer


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def _read_text(path: Path, max_chars: int = 200_000) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")[:max_chars]
    except Exception:
        return ""
    return ""


def _latest_dir(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.name)[-1]


def _sanitize_numbers(text: str, allowed_corpus: str) -> str:
    """Guardrail: убираем числа, которых нет в источниках (fact-pack/retrieval context)."""

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok in allowed_corpus:
            return tok
        return "NA"

    return re.sub(r"\b\d+(?:\.\d+)?\b", repl, text)


DEFAULT_COPILOT_CFG: Dict[str, Any] = {
    "answer": {
        "strict_source_only": True,
        "require_inline_citations": True,
        "max_facts": 5,
        "max_tables": 3,
        "max_missing_sections": 3,
        "max_sources": 25,
    },
    "llm": {
        "enabled": True,
        "mode": "disabled_when_strict",
        "post_validate_enabled": True,
        "require_target_links": True,
    },
    "resolver": {
        "default_period": "daily",
        "max_rows": 20,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_citation_deep_link(
    *,
    data_version: str,
    section: Optional[str] = None,
    table: Optional[str] = None,
    metric: Optional[str] = None,
    run_id: Optional[str] = None,
    report_version: Optional[str] = None,
    fact_id: Optional[str] = None,
) -> str:
    query = {
        "data_version": str(data_version or "NA"),
        "section": str(section or ""),
        "table": str(table or ""),
        "metric": str(metric or ""),
        "run_id": str(run_id or ""),
        "report_version": str(report_version or ""),
        "fact_id": str(fact_id or ""),
    }
    return "genomeai://copilot/fact?" + urlencode(query)


def load_copilot_answer_config(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(cfg_path) if cfg_path is not None else (_project_root() / "configs" / "copilot" / "copilot_v2.yaml")
    raw: Dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded
    return _deep_merge(DEFAULT_COPILOT_CFG, raw)


@dataclass
class Citation:
    label: str
    source: str
    data_version: str
    period: str
    asof_date: str
    run_id: Optional[str] = None
    model_version: Optional[str] = None
    report_version: Optional[str] = None
    section: Optional[str] = None
    table: Optional[str] = None
    metric: Optional[str] = None
    fact_id: Optional[str] = None
    deep_link: Optional[str] = None


@dataclass
class GuardrailDecision:
    allowed: bool
    reason: str
    disclaimer: str


@dataclass
class AssistantResponse:
    schema: str
    created_at_utc: str
    query_id: str
    question: str
    answer: str
    used_llm: bool
    citations: List[Dict[str, Any]]
    versions: Dict[str, Any]
    guardrails: Dict[str, Any]
    matched_chunk_ids: List[str]
    suggested_followups: List[str]
    tool_trace: List[Dict[str, Any]]


@dataclass
class Chunk:
    chunk_id: str
    text: str
    citations: List[Citation]


def evaluate_guardrails(question: str) -> GuardrailDecision:
    q = (question or "").strip().lower()
    # Requests for diagnosis/treatment are prohibited
    diag_kw = [
        "диагноз",
        "лечи",
        "лечение",
        "антибиотик",
        "мастит ли",
        "точно мастит",
        "поставь диагноз",
    ]
    if any(k in q for k in diag_kw):
        return GuardrailDecision(
            allowed=False,
            reason="diagnosis_or_treatment_request",
            disclaimer=(
                "Я не ставлю диагнозы и не назначаю лечение. Могу показать только риск/факты и предложить действия "
                "в формате decision-support (осмотр/проба/перепроверка данных) с указанием источников."
            ),
        )

    # Out-of-scope (non-system knowledge)
    oos_kw = ["погода", "курс", "новости", "википедия", "интернет", "как сделать" ]
    if any(k in q for k in oos_kw):
        return GuardrailDecision(
            allowed=False,
            reason="out_of_scope_non_system",
            disclaimer=(
                "Я отвечаю только по данным и артефактам GenomeAI AgroAnimals (витрины, алерты, отчёты, decision log). "
                "Запрос вне области данных системы."
            ),
        )

    return GuardrailDecision(
        allowed=True,
        reason="ok",
        disclaimer=(
            "Decision-support: рекомендации носят справочный характер и основаны только на данных системы. "
            "При необходимости подтвердите действие — запись попадёт в Decision Log."
        ),
    )


def build_fact_pack_for_assistant(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str,
    web_db_path: Optional[Path] = None,
    max_rows: int = 50,
) -> Dict[str, Any]:
    """Собирает fact-pack для RAG. Основа — T8-01 fact_pack_regular + добавки (decision log, отчёты)."""

    fp = build_fact_pack_regular(
        artifacts_root=Path(artifacts_root),
        data_version=str(data_version),
        asof_date=str(asof_date),
        period=str(period),
        max_rows=int(max_rows),
    )

    dv = str(data_version)
    base: Dict[str, Any] = {
        "available": False,
        "top": [],
        "sources": {},
    }

    # Legacy decision log (csv/jsonl in artifacts)
    d_csv = Path(artifacts_root) / dv / "decisions" / "decision_log.csv"
    d_df = _safe_read_csv(d_csv)
    legacy = dict(base)
    if not d_df.empty:
        legacy = {
            "available": True,
            "count": int(d_df.shape[0]),
            "top": json.loads(d_df.tail(min(max_rows, 50)).fillna("").to_json(orient="records", force_ascii=False)),
            "sources": {"decision_log_csv": str(d_csv.resolve())},
        }

    # Decision log v2 (SQLite web.db), best-effort
    v2 = dict(base)
    if web_db_path and Path(web_db_path).exists():
        try:
            conn = _pg_connect()
            rows = conn.execute(
                "SELECT created_at, action, username, object_type, object_id, related_alert, data_version, model_version, report_version, reason "
                "FROM decision_log_v2 ORDER BY id DESC LIMIT ?",
                (int(max_rows),),
            ).fetchall()
            conn.close()
            if rows:
                v2 = {
                    "available": True,
                    "count": int(len(rows)),
                    "top": [dict(r) for r in rows],
                    "sources": {"web_db": str(Path(web_db_path).resolve()), "table": "decision_log_v2"},
                }
        except Exception:
            pass

    # Tasks v1 (SQLite web.db), best-effort
    tasks_v1 = dict(base)
    if web_db_path and Path(web_db_path).exists():
        try:
            conn = _pg_connect()
            total_row = conn.execute("SELECT COUNT(1) AS c FROM tasks_v1").fetchone()
            rows = conn.execute(
                "SELECT task_id, task_type, title, status, priority, domain, assignee_team, due_at, related_alert, object_type, object_id, qc_run, model_version, scoring_run, report_version, data_version, updated_at "
                "FROM tasks_v1 ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (int(max_rows),),
            ).fetchall()
            open_row = conn.execute(
                "SELECT COUNT(1) AS c FROM tasks_v1 WHERE COALESCE(status,'') NOT IN ('done','cancelled','archived')"
            ).fetchone()
            overdue_row = conn.execute(
                "SELECT COUNT(1) AS c FROM tasks_v1 WHERE due_at IS NOT NULL AND due_at <> '' AND due_at < datetime('now') AND COALESCE(status,'') NOT IN ('done','cancelled','archived')"
            ).fetchone()
            conn.close()
            total_count = int(dict(total_row).get('c', 0)) if total_row is not None else 0
            open_count = int(dict(open_row).get('c', 0)) if open_row is not None else 0
            overdue_count = int(dict(overdue_row).get('c', 0)) if overdue_row is not None else 0
            tasks_v1 = {
                "available": bool(total_count > 0),
                "count": total_count,
                "open_count": open_count,
                "overdue_count": overdue_count,
                "top": [dict(r) for r in rows],
                "sources": {"web_db": str(Path(web_db_path).resolve()), "table": "tasks_v1"},
            }
        except Exception:
            pass

    # Latest regular report exports (MD)
    rep_block = dict(base)
    rep_root = Path(artifacts_root) / dv / "reports_regular"
    rep_ver = _latest_dir(rep_root)
    if rep_ver is not None:
        md_dir = rep_ver / "exports"
        director_md = md_dir / "report_director.md"
        ops_md = md_dir / "report_ops.md"
        rep_block = {
            "available": True,
            "report_version": rep_ver.name,
            "director_md": _read_text(director_md, max_chars=120_000),
            "ops_md": _read_text(ops_md, max_chars=120_000),
            "sources": {
                "director_md": str(director_md.resolve()) if director_md.exists() else "NA",
                "ops_md": str(ops_md.resolve()) if ops_md.exists() else "NA",
            },
        }

    # T12-03: Playbooks (active versions if web DB has them; else defaults.yaml)
    pb_block = list_active_playbooks(
        tenant_id="default",
        web_db_path=Path(web_db_path) if web_db_path else None,
        limit=60,
    )

    # T14-05: Feedback loop summary from web.db (best-effort, filtered by current data_version)
    feedback_block = dict(base)
    if web_db_path and Path(web_db_path).exists():
        try:
            conn = _pg_connect()
            feedback_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM feedback_events_v1 WHERE COALESCE(data_version, '') IN ('', ?) ORDER BY created_at DESC, id DESC LIMIT ?",
                    (dv, int(max_rows * 4)),
                ).fetchall()
            ]
            task_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT task_id, related_alert, object_type, object_id, status, closed_reason, closed_at, updated_at FROM tasks_v1 ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                    (int(max_rows * 4),),
                ).fetchall()
            ]
            conn.close()
            cfg = load_feedback_config(Path(__file__).resolve().parents[2] / FEEDBACK_CFG_PATH)
            fb_metrics = core_compute_feedback_metrics(feedback_rows, task_rows, cfg=cfg)
            if int(fb_metrics.get("feedback_total") or 0) > 0:
                feedback_block = {
                    "available": True,
                    "window_days": int(fb_metrics.get("window_days") or cfg.default_window_days),
                    "feedback_total": int(fb_metrics.get("feedback_total") or 0),
                    "accepted_total": int(fb_metrics.get("accepted_total") or 0),
                    "rejected_total": int(fb_metrics.get("rejected_total") or 0),
                    "acceptance_rate": float(fb_metrics.get("acceptance_rate") or 0.0),
                    "median_time_to_decision_hours": fb_metrics.get("median_time_to_decision_hours"),
                    "top_accept_reason_code": fb_metrics.get("top_accept_reason_code"),
                    "top_reject_reason_code": fb_metrics.get("top_reject_reason_code"),
                    "rejection_reasons": list(fb_metrics.get("rejection_reasons") or [])[:5],
                    "by_feedback_source": list(fb_metrics.get("by_feedback_source") or [])[:5],
                    "by_scoring_run": list(fb_metrics.get("by_scoring_run") or [])[:5],
                    "by_report_version": list(fb_metrics.get("by_report_version") or [])[:5],
                    "task_outcomes_by_decision": list(fb_metrics.get("task_outcomes_by_decision") or [])[:8],
                    "recommendation_context_preview": list(fb_metrics.get("recommendation_context_preview") or [])[:10],
                    "sources": {
                        "web_db": str(Path(web_db_path).resolve()),
                        "feedback_events_v1": "feedback_events_v1",
                        "tasks_v1": "tasks_v1",
                    },
                }
        except Exception:
            pass

    fp["assistant_knowledge"] = {
        "schema": "genomeai.fact_pack.assistant.v1",
        "decision_log_legacy": legacy,
        "decision_log_v2": v2,
        "regular_reports_latest": rep_block,
        "playbooks": pb_block,
        "tasks_v1": tasks_v1,
        "feedback_loop": feedback_block,
    }
    fp["copilot_fact_pack"] = build_copilot_fact_pack_from_assistant_fact_pack(fp)
    return fp


def build_chunks_from_fact_pack(fact_pack: Dict[str, Any]) -> List[Chunk]:
    v = fact_pack.get("versions", {}) or {}
    dv = str(v.get("data_version", "NA"))
    model_version = str(v.get("model_version", "NA"))
    period = str(fact_pack.get("period", "NA"))
    asof_date = str(fact_pack.get("asof_date", "NA"))

    chunks: List[Chunk] = []

    def add_chunk(
        label: str,
        text: str,
        sources: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        report_version: Optional[str] = None,
        section: Optional[str] = None,
        table: Optional[str] = None,
        metric: Optional[str] = None,
        fact_id: Optional[str] = None,
    ) -> None:
        if not text.strip():
            return
        cits: List[Citation] = []
        if isinstance(sources, dict) and sources:
            for k, src in sources.items():
                src_section = section
                src_table = table
                src_run_id = run_id
                src_report_version = report_version
                src_model_version = model_version
                if isinstance(src, dict):
                    src_section = str(src.get("section") or src_section or "") or None
                    src_table = str(src.get("table") or src_table or "") or None
                    src_run_id = str(src.get("run_id") or src_run_id or "") or None
                    src_report_version = str(src.get("report_version") or src_report_version or "") or None
                    src_model_version = str(src.get("model_version") or src_model_version or "") or None
                    src = src.get("ref") or src.get("source") or src.get("path") or json.dumps(src, ensure_ascii=False)
                cits.append(
                    Citation(
                        label=f"{label}.{k}",
                        source=str(src),
                        data_version=dv,
                        model_version=src_model_version,
                        period=period,
                        asof_date=asof_date,
                        run_id=src_run_id,
                        report_version=src_report_version,
                        section=src_section,
                        table=src_table,
                        metric=metric,
                        fact_id=fact_id,
                        deep_link=_build_citation_deep_link(
                            data_version=dv,
                            section=src_section,
                            table=src_table,
                            metric=metric,
                            run_id=src_run_id,
                            report_version=src_report_version or "NA",
                            fact_id=fact_id,
                        ),
                    )
                )
        else:
            cits.append(
                Citation(
                    label=label,
                    source="NA",
                    data_version=dv,
                    model_version=model_version,
                    period=period,
                    asof_date=asof_date,
                    run_id=run_id,
                    report_version=report_version,
                    section=section,
                    table=table,
                    metric=metric,
                    fact_id=fact_id,
                    deep_link=_build_citation_deep_link(
                        data_version=dv,
                        section=section,
                        table=table,
                        metric=metric,
                        run_id=run_id,
                        report_version=report_version,
                        fact_id=fact_id,
                    ),
                )
            )

        chunks.append(Chunk(chunk_id=uuid.uuid4().hex, text=text, citations=cits))

    copilot = fact_pack.get("copilot_fact_pack") or {}
    if isinstance(copilot, dict) and copilot.get("schema") == "genomeai.copilot.fact_pack.v1":
        source_registry = copilot.get("sources") or {}
        for fact in (copilot.get("facts") or []):
            if not isinstance(fact, dict):
                continue
            source_ids = list(fact.get("source_ids") or [])
            fact_sources = {sid: source_registry.get(sid) for sid in source_ids if sid in source_registry}
            metric_name = str(fact.get("metric_name") or "metric")
            value = fact.get("value")
            text = (
                f"[fact] section={fact.get('section')} metric={metric_name} value={value} "
                f"run_id={fact.get('run_id') or 'NA'} report_version={fact.get('report_version') or 'NA'} "
                f"fact_id={fact.get('fact_id')}"
            )
            add_chunk(
                str(fact.get("fact_id") or metric_name),
                text,
                fact_sources,
                run_id=str(fact.get("run_id") or "") or None,
                report_version=str(fact.get("report_version") or "") or None,
                section=str(fact.get("section") or "") or None,
                metric=metric_name,
                fact_id=str(fact.get("fact_id") or "") or None,
            )

        for table_block in (copilot.get("tables") or []):
            if not isinstance(table_block, dict):
                continue
            source_ids = list(table_block.get("source_ids") or [])
            table_sources = {sid: source_registry.get(sid) for sid in source_ids if sid in source_registry}
            rows = table_block.get("rows") or []
            preview = json.dumps(rows[:3], ensure_ascii=False)
            text = (
                f"[table] section={table_block.get('section')} table={table_block.get('table')} row_count={table_block.get('row_count')} "
                f"run_id={table_block.get('run_id') or 'NA'} table_id={table_block.get('table_id')} preview={preview}"
            )
            add_chunk(
                str(table_block.get("table_id") or table_block.get("table") or "table"),
                text,
                table_sources,
                run_id=str(table_block.get("run_id") or "") or None,
                report_version=str(table_block.get("report_version") or "") or None,
                section=str(table_block.get("section") or "") or None,
                table=str(table_block.get("table") or "") or None,
                fact_id=str(table_block.get("table_id") or "") or None,
            )

        for req in (copilot.get("missing_data_requests") or []):
            if not isinstance(req, dict):
                continue
            text = (
                f"[missing_data_request] section={req.get('section')} why={req.get('why')} "
                f"needed_data={json.dumps(req.get('needed_data') or [], ensure_ascii=False)} "
                f"how_to_get={json.dumps(req.get('how_to_get') or [], ensure_ascii=False)}"
            )
            add_chunk(
                str(req.get("request_id") or f"missing.{req.get('section') or 'na'}"),
                text,
                {},
                section=str(req.get("section") or "") or None,
                fact_id=str(req.get("request_id") or "") or None,
            )

        if chunks:
            return chunks

    mods = fact_pack.get("modules", {}) or {}
    for mod_name, block in mods.items():
        if not isinstance(block, dict):
            continue
        add_chunk(
            f"modules.{mod_name}.summary",
            json.dumps(block, ensure_ascii=False)[:120_000],
            (block.get("sources") or {}),
            run_id=block.get("run_id") or block.get("economics_run") or block.get("scoring_run"),
            section=f"modules.{mod_name}",
        )

    ak = fact_pack.get("assistant_knowledge", {}) or {}
    if isinstance(ak, dict):
        legacy = ak.get("decision_log_legacy") or {}
        if isinstance(legacy, dict) and legacy.get("available"):
            add_chunk(
                "decision_log.legacy",
                json.dumps(legacy.get("top") or [], ensure_ascii=False),
                legacy.get("sources") or {},
                section="assistant_knowledge.decision_log_legacy",
            )
        v2 = ak.get("decision_log_v2") or {}
        if isinstance(v2, dict) and v2.get("available"):
            add_chunk(
                "decision_log.v2",
                json.dumps(v2.get("top") or [], ensure_ascii=False),
                v2.get("sources") or {},
                section="assistant_knowledge.decision_log_v2",
            )

        rep = ak.get("regular_reports_latest") or {}
        if isinstance(rep, dict) and rep.get("available"):
            text = "\n\n".join([
                "[director_md]\n" + (rep.get("director_md") or ""),
                "[ops_md]\n" + (rep.get("ops_md") or ""),
            ])
            add_chunk(
                "regular_reports.latest",
                text,
                rep.get("sources") or {},
                report_version=str(rep.get("report_version")) if rep.get("report_version") else None,
                section="assistant_knowledge.regular_reports_latest",
            )

        pb = ak.get("playbooks") or {}
        if isinstance(pb, dict) and (pb.get("active") or []):
            for p in (pb.get("active") or [])[:60]:
                try:
                    kind = str(p.get("target_kind") or "NA")
                    tp = str(p.get("target_type") or "NA")
                    fid = str(p.get("farm_id") or "")
                    vid = str(p.get("version_id") or "NA")
                    name = str(p.get("name") or "NA")
                    desc = str(p.get("description") or "").strip()
                    steps = list(p.get("steps") or [])
                    lines = [
                        "[playbook]",
                        f"target_kind={kind}",
                        f"target_type={tp}",
                        f"farm_id={fid or 'GLOBAL'}",
                        f"version_id={vid}",
                        f"name={name}",
                    ]
                    if desc:
                        lines.append(f"description={desc}")
                    if steps:
                        lines.append("steps:")
                        for i, st in enumerate(steps[:12], start=1):
                            title = str(st.get("title") or st.get("key") or "step")
                            details = str(st.get("details") or "").strip()
                            if details:
                                lines.append(f"{i}) {title}: {details}")
                            else:
                                lines.append(f"{i}) {title}")
                    lines.append("[/playbook]")
                    add_chunk(
                        f"playbook.{kind}.{tp}",
                        "\n".join(lines),
                        (p.get("sources") or pb.get("sources") or {}),
                        report_version=None,
                        section=f"assistant_knowledge.playbooks.{kind}.{tp}",
                    )
                except Exception:
                    continue

    return chunks


def retrieve_chunks(question: str, chunks: List[Chunk], *, top_k: int = 6) -> List[Chunk]:
    if not chunks:
        return []
    texts = [c.text for c in chunks]
    vec = TfidfVectorizer(max_features=20_000, ngram_range=(1, 2))
    X = vec.fit_transform(texts)
    qv = vec.transform([question])
    sims = cosine_similarity(qv, X).ravel()
    idx = sims.argsort()[::-1][: int(top_k)]
    return [chunks[i] for i in idx if sims[i] > 0]


def _dedupe_citations(citations: List[Citation]) -> List[Citation]:
    uniq: Dict[Tuple[str, str, str, str], Citation] = {}
    for c in citations or []:
        uniq[(str(c.label), str(c.source), str(c.fact_id or ""), str(c.metric or c.table or ""))] = c
    return list(uniq.values())


def _chunk_citations(ch: Chunk) -> List[Citation]:
    return _dedupe_citations(list(ch.citations or []))


def _inline_citation(ch: Chunk) -> str:
    citations = _chunk_citations(ch)
    if not citations:
        return "[Источник: fact_id=NA; section=NA; table=NA; metric=NA; run_id=NA; report_version=NA]"
    parts: List[str] = []
    for c in citations[:2]:
        parts.append(
            "fact_id={fact_id}; section={section}; table={table}; metric={metric}; run_id={run_id}; report_version={report_version}; target={target}".format(
                fact_id=c.fact_id or "NA",
                section=c.section or "NA",
                table=c.table or "NA",
                metric=c.metric or "NA",
                run_id=c.run_id or "NA",
                report_version=c.report_version or "NA",
                target=c.deep_link or _build_citation_deep_link(
                    data_version=c.data_version,
                    section=c.section,
                    table=c.table,
                    metric=c.metric,
                    run_id=c.run_id,
                    report_version=c.report_version,
                    fact_id=c.fact_id,
                ),
            )
        )
    return "[Источник: " + " || ".join(parts) + "]"


def _first_citation(ch: Chunk) -> Optional[Citation]:
    citations = _chunk_citations(ch)
    return citations[0] if citations else None


def _parse_fact_chunk(ch: Chunk) -> Dict[str, str]:
    text = ch.text or ""
    value_match = re.search(r" value=(.*?) run_id=", text)
    return {
        "section": next((str(c.section or "") for c in ch.citations if c.section), "NA"),
        "metric": next((str(c.metric or "") for c in ch.citations if c.metric), "NA"),
        "value": (value_match.group(1).strip() if value_match else "NA"),
        "run_id": next((str(c.run_id or "") for c in ch.citations if c.run_id), "NA") or "NA",
        "report_version": next((str(c.report_version or "") for c in ch.citations if c.report_version), "NA") or "NA",
        "fact_id": next((str(c.fact_id or "") for c in ch.citations if c.fact_id), "NA") or "NA",
    }


def _parse_table_chunk(ch: Chunk) -> Dict[str, str]:
    text = ch.text or ""
    table_name = re.search(r" table=(.*?) row_count=", text)
    row_count = re.search(r" row_count=(.*?) run_id=", text)
    preview = re.search(r" preview=(.*)$", text)
    return {
        "section": next((str(c.section or "") for c in ch.citations if c.section), "NA"),
        "table": (table_name.group(1).strip() if table_name else next((str(c.table or "") for c in ch.citations if c.table), "NA")),
        "row_count": (row_count.group(1).strip() if row_count else "NA"),
        "preview": (preview.group(1).strip() if preview else "[]"),
        "run_id": next((str(c.run_id or "") for c in ch.citations if c.run_id), "NA") or "NA",
        "report_version": next((str(c.report_version or "") for c in ch.citations if c.report_version), "NA") or "NA",
        "fact_id": next((str(c.fact_id or "") for c in ch.citations if c.fact_id), "NA") or "NA",
    }


def _parse_missing_chunk(ch: Chunk) -> Dict[str, Any]:
    text = ch.text or ""
    needed: List[str] = []
    how: List[str] = []
    m1 = re.search(r"needed_data=(\[.*?\])", text)
    m2 = re.search(r"how_to_get=(\[.*\])", text)
    if m1:
        try:
            needed = json.loads(m1.group(1))
        except Exception:
            needed = []
    if m2:
        try:
            how = json.loads(m2.group(1))
        except Exception:
            how = []
    return {
        "section": next((str(c.section or "") for c in ch.citations if c.section), "NA"),
        "needed_data": needed,
        "how_to_get": how,
    }


def _is_primary_evidence(ch: Chunk) -> bool:
    sections = [str(c.section or "") for c in (ch.citations or [])]
    if not sections:
        return False
    return any(
        s.startswith("modules.")
        or s.startswith("assistant_knowledge.decision_log")
        or s.startswith("assistant_knowledge.tasks_v1")
        or s.startswith("assistant_knowledge.feedback_loop")
        for s in sections
    )


def _parse_inline_citation_segments(text: str) -> List[Dict[str, str]]:
    segments: List[Dict[str, str]] = []
    for block in re.findall(r"\[Источник:\s*(.*?)\]", text or ""):
        for raw_seg in [part.strip() for part in block.split("||") if part.strip()]:
            payload: Dict[str, str] = {}
            for item in [x.strip() for x in raw_seg.split(";") if x.strip()]:
                if "=" not in item:
                    continue
                key, value = item.split("=", 1)
                payload[key.strip()] = value.strip()
            if payload:
                segments.append(payload)
    return segments


def _citation_segment_matches_allowed(
    segment: Dict[str, str],
    allowed: List[Citation],
    *,
    require_target_links: bool = True,
) -> bool:
    fact_id = str(segment.get("fact_id") or "NA")
    section = str(segment.get("section") or "NA")
    table = str(segment.get("table") or "NA")
    metric = str(segment.get("metric") or "NA")
    run_id = str(segment.get("run_id") or "NA")
    report_version = str(segment.get("report_version") or "NA")
    target = str(segment.get("target") or "")
    for c in allowed:
        c_target = c.deep_link or _build_citation_deep_link(
            data_version=c.data_version,
            section=c.section,
            table=c.table,
            metric=c.metric,
            run_id=c.run_id,
            report_version=c.report_version,
            fact_id=c.fact_id,
        )
        if (
            fact_id == str(c.fact_id or "NA")
            and section == str(c.section or "NA")
            and table == str(c.table or "NA")
            and metric == str(c.metric or "NA")
            and run_id == str(c.run_id or "NA")
            and report_version == str(c.report_version or "NA")
            and ((not require_target_links and (not target or target == c_target)) or (require_target_links and target == c_target))
        ):
            return True
    return False


def _line_requires_citation(line: str) -> bool:
    value = str(line or "").strip()
    if not value:
        return False
    if value.endswith(":"):
        return False
    if value.startswith("Ответ сформирован") or value.startswith("Вопрос:") or value.startswith("Decision-support"):
        return False
    if value.startswith("Источники/версии") or value.startswith("- src"):
        return False
    if value.startswith("Нужны данные") or value.startswith("Как получить") or value.startswith("Trace versions"):
        return False
    return bool(re.search(r"\d", value) or value.startswith("-") or "=" in value or "row_count=" in value)


def _post_validate_llm_answer(
    text: str,
    *,
    retrieved: List[Chunk],
    require_target_links: bool = True,
) -> Tuple[bool, str]:
    value = (text or "").strip()
    if not value:
        return False, "empty_answer"
    allowed: List[Citation] = []
    for ch in retrieved:
        allowed.extend(ch.citations or [])
    allowed = _dedupe_citations(allowed)
    if not allowed:
        return False, "no_allowed_citations"

    segments = _parse_inline_citation_segments(value)
    if not segments:
        return False, "missing_inline_citations"
    for seg in segments:
        if require_target_links and not str(seg.get("target") or "").strip():
            return False, "missing_target_link"
        if not _citation_segment_matches_allowed(seg, allowed, require_target_links=require_target_links):
            return False, "unsupported_inline_citation"

    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not _line_requires_citation(line):
            continue
        if "[Источник:" not in line:
            return False, "line_without_inline_citation"
    return True, "ok"


def _write_assistant_audit_best_effort(
    *,
    web_db_path: Optional[Path],
    action: str,
    data_version: str,
    run_id: Optional[str],
    object_id: str,
    status: str = "OK",
    after: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    if not web_db_path:
        return
    try:
        from core.audit.events import write_audit
        from core.infra.postgres_compat import connect_postgres_compat as _pg_connect
from core.infra.web_db import connect, init_db

        db_path = Path(web_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(db_path)
        init_db(conn)
        write_audit(
            conn,
            tenant_id="default",
            user_id=0,
            username="system",
            role="system",
            action=action,
            object_type="copilot",
            object_id=object_id,
            data_version=data_version,
            run_id=run_id,
            after=after,
            status=status,
            error=error,
        )
        conn.close()
    except Exception:
        return





def _parse_table_preview_rows(ch: Chunk) -> List[Dict[str, Any]]:
    payload = _parse_table_chunk(ch)
    raw = str(payload.get("preview") or "[]").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [dict(x) for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _format_row_compact(row: Dict[str, Any], preferred_keys: Optional[Sequence[str]] = None, *, max_items: int = 6) -> str:
    if not isinstance(row, dict):
        return "{}"
    ordered_keys: List[str] = []
    for key in list(preferred_keys or []):
        if key in row and key not in ordered_keys:
            ordered_keys.append(key)
    for key in row.keys():
        if key not in ordered_keys:
            ordered_keys.append(str(key))
    parts: List[str] = []
    for key in ordered_keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        parts.append(f"{key}={value}")
        if len(parts) >= int(max_items):
            break
    return "; ".join(parts) if parts else json.dumps(row, ensure_ascii=False)[:300]


def _parse_playbook_chunk(ch: Chunk) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "target_kind": "NA",
        "target_type": "NA",
        "farm_id": "NA",
        "version_id": "NA",
        "name": "NA",
        "description": "",
        "steps": [],
    }
    lines = [line.strip() for line in (ch.text or "").splitlines() if line.strip()]
    in_steps = False
    for line in lines:
        if line == "[playbook]" or line == "[/playbook]":
            continue
        if line == "steps:":
            in_steps = True
            continue
        if in_steps and re.match(r"^\d+\)\s+", line):
            payload.setdefault("steps", []).append(line)
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key in payload:
                payload[key] = value.strip()
    return payload


def _tool_source_only_answer(
    question: str,
    retrieved: List[Chunk],
    disclaimer: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    tool_result: Any = None,
) -> Tuple[str, List[Citation], List[str]]:
    if tool_result is None:
        return _source_only_answer(question, retrieved, disclaimer, cfg=cfg)

    config = cfg or load_copilot_answer_config()
    answer_cfg = config.get("answer", {}) or {}
    max_facts = int(answer_cfg.get("max_facts", 5))
    max_tables = int(answer_cfg.get("max_tables", 3))
    max_missing_sections = int(answer_cfg.get("max_missing_sections", 3))

    citations: List[Citation] = []
    for ch in retrieved:
        citations.extend(ch.citations or [])
    citations = _dedupe_citations(citations)

    decision = getattr(tool_result, "decision", None)
    spec = getattr(tool_result, "query_spec", None)
    tool_name = str(getattr(decision, "tool_name", "") or "")
    intent = str(getattr(spec, "intent", "overview") or "overview")

    missing_chunks = [c for c in retrieved if "[missing_data_request]" in (c.text or "")]
    fact_chunks = [c for c in retrieved if "[fact]" in (c.text or "") and _is_primary_evidence(c)][:max_facts]
    table_chunks = [c for c in retrieved if "[table]" in (c.text or "") and _is_primary_evidence(c)][:max_tables]
    task_table_chunks = [c for c in table_chunks if any(str(cit.section or "").startswith("assistant_knowledge.tasks_v1") for cit in (c.citations or []))]
    feedback_table_chunks = [c for c in table_chunks if any(str(cit.section or "").startswith("assistant_knowledge.feedback_loop") for cit in (c.citations or []))]
    feedback_fact_chunks = [c for c in fact_chunks if any(str(cit.section or "").startswith("assistant_knowledge.feedback_loop") for cit in (c.citations or []))]
    playbook_chunks = [
        c for c in retrieved
        if "[playbook]" in (c.text or "")
        or ("[table]" in (c.text or "") and any(str(cit.section or "").startswith("assistant_knowledge.playbooks") for cit in (c.citations or [])))
    ]

    if missing_chunks and not fact_chunks and not table_chunks:
        return _source_only_answer(question, retrieved, disclaimer, cfg=cfg)

    def append_missing(lines: List[str]) -> None:
        if not missing_chunks:
            return
        lines.append("")
        lines.append("Для более точного ответа ещё нужны данные:")
        for ch in missing_chunks[:max_missing_sections]:
            payload = _parse_missing_chunk(ch)
            lines.append(f"- Раздел {payload['section']} {_inline_citation(ch)}")
            for item in payload.get("needed_data") or []:
                lines.append(f"  - {item}")

    lines: List[str] = [
        "Ответ сформирован только по подтверждённым данным copilot_fact_pack.",
        f"Вопрос: {question}",
    ]

    if tool_name == "query_anomalies" and intent == "why":
        lines.extend(["", "Почему Copilot считает это отклонением:"])
        for ch in fact_chunks[:3]:
            payload = _parse_fact_chunk(ch)
            lines.append(f"- Сигнал: {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(ch)}")
        for ch in table_chunks[:2]:
            payload = _parse_table_chunk(ch)
            rows = _parse_table_preview_rows(ch)
            lines.append(f"- Подтверждающая выборка: {payload['section']}.{payload['table']} | row_count={payload['row_count']} {_inline_citation(ch)}")
            why_text, cf_text = _extract_explainability_from_rows(rows, question)
            if why_text:
                lines.append(f"  - Top factors: {why_text} {_inline_citation(ch)}")
            if cf_text:
                lines.append(f"  - Простой контрфакт: {cf_text} {_inline_citation(ch)}")
        if playbook_chunks:
            lines.extend(["", "Что проверить/сделать:"])
            for ch in playbook_chunks[:2]:
                if "[playbook]" in (ch.text or ""):
                    pb = _parse_playbook_chunk(ch)
                    step = (pb.get("steps") or ["шаги отсутствуют"])[0]
                    label = f"Playbook {pb.get('name')} | первый шаг: {step}"
                else:
                    rows = _parse_table_preview_rows(ch)
                    first = rows[0] if rows else {}
                    label = _format_row_compact(first, ["name", "target_type", "version_id", "farm_id"], max_items=5)
                lines.append(f"- {label} {_inline_citation(ch)}")
        append_missing(lines)
        followups = ["Показать связанные задачи по этому отклонению?", "Открыть таблицу/скоринг по citation target?"]
        lines.extend(["", disclaimer])
        return "\n".join(lines).strip(), citations, followups

    if tool_name == "query_tasks" and feedback_table_chunks:
        lines.extend(["", "Feedback loop по рекомендациям:"])
        for ch in feedback_fact_chunks[:4]:
            payload = _parse_fact_chunk(ch)
            metric = str(payload.get("metric") or "")
            if metric in {"feedback_total", "accepted_total", "rejected_total", "acceptance_rate", "median_time_to_decision_hours", "top_accept_reason_code", "top_reject_reason_code"}:
                lines.append(f"- Метрика: {payload['section']}.{metric} = {payload['value']} {_inline_citation(ch)}")
        for ch in feedback_table_chunks[:3]:
            payload = _parse_table_chunk(ch)
            rows = _parse_table_preview_rows(ch)
            if payload.get("table") == "rejection_reasons" and rows:
                first = rows[0]
                compact = _format_row_compact(first, ["reason_code", "count"], max_items=3)
                lines.append(f"- Топ причины отказа: {compact} {_inline_citation(ch)}")
                continue
            if payload.get("table") == "by_scoring_run" and rows:
                first = rows[0]
                compact = _format_row_compact(first, ["scoring_run", "feedback_total", "acceptance_rate"], max_items=4)
                lines.append(f"- По scoring_run: {compact} {_inline_citation(ch)}")
                continue
            if payload.get("table") == "by_report_version" and rows:
                first = rows[0]
                compact = _format_row_compact(first, ["report_version", "feedback_total", "acceptance_rate"], max_items=4)
                lines.append(f"- По report_version: {compact} {_inline_citation(ch)}")
                continue
            if payload.get("table") == "recommendation_context_preview" and rows:
                best = _pick_best_row_for_question(rows, question)
                compact = _format_row_compact(best, ["recommendation_id", "decision", "reason_code", "object_id", "scoring_run", "report_version", "task_status"], max_items=7)
                lines.append(f"- Контекст рекомендации: {compact} {_inline_citation(ch)}")
                continue
            lines.append(f"- Таблица feedback: {payload['section']}.{payload['table']} | row_count={payload['row_count']} {_inline_citation(ch)}")
        append_missing(lines)
        followups = ["Показать feedback только по scoring_run?", "Нужно выгрузить feedback dataset для калибровки?"]
        lines.extend(["", disclaimer])
        return "\n".join(lines).strip(), citations, followups

    if tool_name == "query_tasks" and intent == "what_to_do":
        lines.extend(["", "Что делать сейчас:"])
        for ch in task_table_chunks[:2]:
            rows = _parse_table_preview_rows(ch)
            if not rows:
                payload = _parse_table_chunk(ch)
                lines.append(f"- Таблица задач: {payload['section']}.{payload['table']} | row_count={payload['row_count']} {_inline_citation(ch)}")
                continue
            for row in rows[: max(1, min(3, getattr(spec, 'top_n', 3) or 3))]:
                compact = _format_row_compact(row, ["task_id", "title", "status", "priority", "assignee_team", "object_id", "related_alert"], max_items=7)
                lines.append(f"- {compact} {_inline_citation(ch)}")
        if playbook_chunks:
            lines.extend(["", "Дополнительный playbook:"])
            for ch in playbook_chunks[:1]:
                if "[playbook]" in (ch.text or ""):
                    pb = _parse_playbook_chunk(ch)
                    step = (pb.get("steps") or ["шаги отсутствуют"])[0]
                    label = f"{pb.get('name')} | первый шаг: {step}"
                else:
                    rows = _parse_table_preview_rows(ch)
                    first = rows[0] if rows else {}
                    label = _format_row_compact(first, ["name", "target_type", "version_id", "farm_id"], max_items=5)
                lines.append(f"- {label} {_inline_citation(ch)}")
        for ch in table_chunks:
            if ch in task_table_chunks:
                continue
            payload = _parse_table_chunk(ch)
            lines.append(f"- Контекст: {payload['section']}.{payload['table']} | row_count={payload['row_count']} {_inline_citation(ch)}")
        append_missing(lines)
        followups = ["Показать только открытые задачи?", "Нужно открыть карточку задачи/алерта по citation target?"]
        lines.extend(["", disclaimer])
        return "\n".join(lines).strip(), citations, followups

    if tool_name == "query_economics" and intent == "cost":
        lines.extend(["", "Подтверждённая экономика:"])
        for ch in fact_chunks[:3]:
            payload = _parse_fact_chunk(ch)
            lines.append(f"- Метрика: {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(ch)}")
        for ch in table_chunks[:2]:
            rows = _parse_table_preview_rows(ch)
            if rows:
                for row in rows[: max(1, min(3, getattr(spec, 'top_n', 3) or 3))]:
                    compact = _format_row_compact(row, ["farm_id", "revenue_milk", "margin_total", "cost_total", "scenario_name"], max_items=6)
                    payload_json = json.dumps(row, ensure_ascii=False)
                    lines.append(f"- Строка экономики: {compact} | preview={payload_json} {_inline_citation(ch)}")
            else:
                payload = _parse_table_chunk(ch)
                lines.append(f"- Таблица: {payload['section']}.{payload['table']} | row_count={payload['row_count']} {_inline_citation(ch)}")
        append_missing(lines)
        followups = ["Показать детали по farm_id?", "Нужно открыть economics-таблицу по citation target?"]
        lines.extend(["", disclaimer])
        return "\n".join(lines).strip(), citations, followups

    return _source_only_answer(question, retrieved, disclaimer, cfg=cfg)


def _source_only_answer(
    question: str,
    retrieved: List[Chunk],
    disclaimer: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Citation], List[str]]:
    """Строгий детерминированный ответ только из copilot_fact_pack с inline-цитированием."""
    config = cfg or load_copilot_answer_config()
    answer_cfg = config.get("answer", {}) or {}
    max_facts = int(answer_cfg.get("max_facts", 5))
    max_tables = int(answer_cfg.get("max_tables", 3))
    max_missing_sections = int(answer_cfg.get("max_missing_sections", 3))

    citations: List[Citation] = []
    for ch in retrieved:
        citations.extend(ch.citations)
    citations = _dedupe_citations(citations)

    missing_chunks = [c for c in retrieved if "[missing_data_request]" in (c.text or "")]
    fact_chunks = [c for c in retrieved if "[fact]" in (c.text or "") and _is_primary_evidence(c)][:max_facts]
    table_chunks = [c for c in retrieved if "[table]" in (c.text or "") and _is_primary_evidence(c)][:max_tables]

    if missing_chunks and not fact_chunks and not table_chunks:
        lines = [
            "Недостаточно фактов в fact-pack для ответа на вопрос.",
            "",
            "Нужны данные и действия для догрузки:",
        ]
        for ch in missing_chunks[:max_missing_sections]:
            payload = _parse_missing_chunk(ch)
            lines.append(f"- Раздел: {payload['section']} {_inline_citation(ch)}")
            if payload["needed_data"]:
                lines.append("  Нужны данные:")
                for item in payload["needed_data"][:5]:
                    lines.append(f"  - {item}")
            if payload["how_to_get"]:
                lines.append("  Как получить:")
                for item in payload["how_to_get"][:5]:
                    lines.append(f"  - {item}")
        lines.append("")
        lines.append(disclaimer)
        return (
            "\n".join(lines).strip(),
            citations,
            ["Запустить нужный offline-core pipeline", "Повторить вопрос после появления run_id и итоговых таблиц"],
        )

    if not retrieved:
        return (
            "NA\n\n" + disclaimer + "\n\n" + "Источники: NA (нет релевантных артефактов)",
            [],
            ["Уточните период/asof_date", "Проверьте, что витрины и алерты построены для выбранной версии данных"],
        )

    lines: List[str] = [
        "Ответ сформирован только по подтверждённым данным copilot_fact_pack.",
        f"Вопрос: {question}",
    ]

    if fact_chunks:
        lines.append("")
        lines.append("Подтверждённые факты:")
        for ch in fact_chunks:
            payload = _parse_fact_chunk(ch)
            lines.append(f"- {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(ch)}")

    if table_chunks:
        lines.append("")
        lines.append("Подтверждённые таблицы/выборки:")
        for ch in table_chunks:
            payload = _parse_table_chunk(ch)
            preview = payload["preview"][:400] + ("…" if len(payload["preview"]) > 400 else "")
            lines.append(
                f"- {payload['section']}.{payload['table']} | row_count={payload['row_count']} | preview={preview} {_inline_citation(ch)}"
            )

    pb_chunks = [c for c in retrieved if "[playbook]" in (c.text or "")]
    if pb_chunks:
        lines.append("")
        lines.append("Рекомендуемый план действий (playbook):")
        for pbch in pb_chunks[:2]:
            pb_text = pbch.text.strip()
            pb_text = pb_text[:1200] + ("…" if len(pb_text) > 1200 else "")
            lines.append(f"- {pb_text} {_inline_citation(pbch)}")

    if not fact_chunks and not table_chunks:
        lines.append("")
        lines.append("Релевантные подтверждённые факты не найдены. Нужна догрузка данных или запуск соответствующего run_id.")

    lines.append("")
    lines.append(disclaimer)
    return (
        "\n".join(lines).strip(),
        citations,
        ["Нужно ли показать исходные таблицы?", "Нужно ли перечислить отсутствующие данные по разделам?"],
    )


def _fallback_answer(question: str, retrieved: List[Chunk], disclaimer: str) -> Tuple[str, List[Citation], List[str]]:
    return _source_only_answer(question, retrieved, disclaimer, cfg=load_copilot_answer_config())


def _render_tool_trace(tool_result: Any) -> str:
    decision = getattr(tool_result, "decision", None)
    spec = getattr(tool_result, "query_spec", None)
    if decision is None or spec is None:
        return ""
    filters: List[str] = []
    if getattr(spec, "farm_id", None):
        filters.append(f"farm_id={spec.farm_id}")
    if getattr(spec, "object_id", None):
        filters.append(f"object_id={spec.object_id}")
    if getattr(spec, "alert_id", None):
        filters.append(f"alert_id={spec.alert_id}")
    if getattr(spec, "severity", None):
        filters.append(f"severity={spec.severity}")
    if getattr(spec, "status", None):
        filters.append(f"status={spec.status}")
    if getattr(spec, "assignee_team", None):
        filters.append(f"assignee_team={spec.assignee_team}")
    if getattr(spec, "period_hint", None):
        filters.append(f"period_hint={spec.period_hint}")
    matched_keywords = ",".join(list(getattr(decision, "matched_keywords", []) or [])) or "NA"
    hidden_sections = ",".join(list(getattr(tool_result, "hidden_section_prefixes", []) or [])) or "NA"
    return (
        f"Tool route: {decision.tool_name} | intent={getattr(spec, 'intent', 'overview')} | "
        f"filters={'; '.join(filters)} | matched_keywords={matched_keywords} | hidden_sections={hidden_sections}"
    )


def _build_tool_trace_entry(tool_result: Any) -> Dict[str, Any]:
    decision = getattr(tool_result, "decision", None)
    spec = getattr(tool_result, "query_spec", None)
    if decision is None or spec is None:
        return {}
    return {
        "tool_name": str(getattr(decision, "tool_name", "") or ""),
        "label": str(getattr(decision, "label", "") or ""),
        "intent": str(getattr(spec, "intent", "overview") or "overview"),
        "score": int(getattr(decision, "score", 0) or 0),
        "route_reason": str(getattr(decision, "route_reason", "") or ""),
        "matched_keywords": list(getattr(decision, "matched_keywords", []) or []),
        "required_permission": getattr(tool_result, "required_permission", None),
        "allowed": bool(getattr(tool_result, "allowed", False)),
        "visible_section_prefixes": list(getattr(tool_result, "visible_section_prefixes", []) or []),
        "hidden_section_prefixes": list(getattr(tool_result, "hidden_section_prefixes", []) or []),
        "query_spec": getattr(spec, "as_dict", lambda: {})(),
        "denial_message": getattr(tool_result, "denial_message", None),
    }


def _strip_generic_tool_wrapper(text: str) -> str:
    out: List[str] = []
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if line.startswith("Ответ сформирован только по подтверждённым данным copilot_fact_pack."):
            continue
        if line.startswith("Вопрос:"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _select_tool_retrieved(tool_result: Any, *, cfg: Dict[str, Any], effective_top_k: int) -> List[Chunk]:
    answer_cfg = cfg.get("answer", {}) or {}
    chunks = build_chunks_from_fact_pack(getattr(tool_result, "filtered_fact_pack", {}) or {})
    retrieved = list(chunks[: max(int(effective_top_k), len(chunks))])
    has_primary_evidence = any(("[fact]" in (c.text or "") or "[table]" in (c.text or "")) and _is_primary_evidence(c) for c in retrieved)
    if not has_primary_evidence:
        missing_candidates = [c for c in chunks if "[missing_data_request]" in (c.text or "")]
        seen_chunk_ids = {c.chunk_id for c in retrieved}
        for ch in missing_candidates[: int(answer_cfg.get("max_missing_sections", 3))]:
            if ch.chunk_id not in seen_chunk_ids:
                retrieved.append(ch)
                seen_chunk_ids.add(ch.chunk_id)
    return retrieved





def _guess_animal_id_from_question(question: str) -> Optional[str]:
    q = str(question or "")
    patterns = [
        r"animal_id\s*[=:]?\s*([A-Za-z0-9_-]+)",
        r"животн(?:ого|ому|ое|ым)?\s*([A-Za-z0-9_-]+)",
        r"коров[аеуы]?\s*([A-Za-z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, q, flags=re.IGNORECASE)
        if m:
            return str(m.group(1))
    return None


def _pick_best_row_for_question(rows: List[Dict[str, Any]], question: str) -> Dict[str, Any]:
    if not rows:
        return {}
    wanted_animal_id = _guess_animal_id_from_question(question)
    if wanted_animal_id:
        for row in rows:
            for key in ["animal_id", "cow_id", "object_id"]:
                if str(row.get(key) or "").strip() == wanted_animal_id:
                    return row
    return rows[0]
def _extract_explainability_from_rows(rows: List[Dict[str, Any]], question: str = "") -> Tuple[Optional[str], Optional[str]]:
    ordered_rows: List[Dict[str, Any]] = []
    preferred = _pick_best_row_for_question(rows or [], question)
    if preferred:
        ordered_rows.append(preferred)
    ordered_rows.extend([r for r in (rows or []) if r is not preferred])
    for row in ordered_rows:
        why = str(row.get("explain_top_factors_text") or row.get("top_factors_text") or "").strip()
        cf = str(row.get("explain_counterfactuals_text") or row.get("counterfactuals_text") or "").strip()
        if why or cf:
            return (why if why and why != "insufficient_explainability_data" else None, cf if cf and cf != "no_simple_counterfactual" else None)
    return None, None

def _tool_plan_title(tool_result: Any) -> str:
    tool_name = str(getattr(getattr(tool_result, "decision", None), "tool_name", "") or "")
    intent = str(getattr(getattr(tool_result, "query_spec", None), "intent", "overview") or "overview")
    if tool_name == "query_anomalies":
        return "Почему / отклонения" if intent == "why" else "Аномалии и алерты"
    if tool_name == "query_tasks":
        return "Что делать" if intent == "what_to_do" else "Задачи"
    if tool_name == "query_economics":
        return "Сколько стоит" if intent == "cost" else "Экономика"
    if tool_name == "query_kpi":
        return "KPI"
    return tool_name or "Раздел"


def _tool_summary_line(tool_result: Any, retrieved: List[Chunk]) -> str:
    tool_name = str(getattr(getattr(tool_result, "decision", None), "tool_name", "") or "")
    fact_chunks = [c for c in retrieved if "[fact]" in (c.text or "") and _is_primary_evidence(c)]
    table_chunks = [c for c in retrieved if "[table]" in (c.text or "") and _is_primary_evidence(c)]
    if tool_name == "query_anomalies":
        for ch in table_chunks:
            rows = _parse_table_preview_rows(ch)
            if rows:
                compact = _format_row_compact(rows[0], ["alert_id", "animal_id", "farm_id", "risk_score", "severity"], max_items=5)
                why_text, cf_text = _extract_explainability_from_rows(rows)
                suffix = ""
                if why_text:
                    suffix += f" | why={why_text}"
                if cf_text:
                    suffix += f" | counterfactual={cf_text}"
                return f"- Почему: {compact}{suffix} {_inline_citation(ch)}"
        if fact_chunks:
            payload = _parse_fact_chunk(fact_chunks[0])
            return f"- Почему: {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(fact_chunks[0])}"
    if tool_name == "query_tasks":
        for ch in table_chunks:
            section = str((ch.citations or [])[0].section or "") if (ch.citations or []) else ""
            payload = _parse_table_chunk(ch)
            rows = _parse_table_preview_rows(ch)
            if section.startswith("assistant_knowledge.feedback_loop") or str(payload.get("section") or "").startswith("assistant_knowledge.feedback_loop"):
                if payload.get("table") == "recommendation_context_preview" and rows:
                    best = _pick_best_row_for_question(rows, "")
                    compact = _format_row_compact(best, ["recommendation_id", "decision", "reason_code", "object_id", "scoring_run"], max_items=5)
                    return f"- Feedback loop: {compact} {_inline_citation(ch)}"
                if payload.get("table") == "rejection_reasons" and rows:
                    compact = _format_row_compact(rows[0], ["reason_code", "count"], max_items=3)
                    return f"- Feedback loop: {compact} {_inline_citation(ch)}"
            if rows:
                compact = _format_row_compact(rows[0], ["task_id", "title", "status", "priority", "assignee_team", "object_id"], max_items=6)
                return f"- Что делать: {compact} {_inline_citation(ch)}"
    if tool_name == "query_economics":
        for ch in table_chunks:
            rows = _parse_table_preview_rows(ch)
            if rows:
                compact = _format_row_compact(rows[0], ["farm_id", "revenue_milk", "margin_total", "cost_total", "scenario_name"], max_items=5)
                return f"- Сколько стоит: {compact} {_inline_citation(ch)}"
        if fact_chunks:
            payload = _parse_fact_chunk(fact_chunks[0])
            return f"- Сколько стоит: {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(fact_chunks[0])}"
    if tool_name == "query_kpi":
        if fact_chunks:
            payload = _parse_fact_chunk(fact_chunks[0])
            return f"- KPI: {payload['section']}.{payload['metric']} = {payload['value']} {_inline_citation(fact_chunks[0])}"
    return ""


def _render_multi_tool_answer(
    *,
    question: str,
    tool_results: List[Any],
    disclaimer: str,
    cfg: Dict[str, Any],
    effective_top_k: int,
) -> Tuple[str, List[Citation], List[str], List[Dict[str, Any]]]:
    allowed_results = [tr for tr in (tool_results or []) if getattr(tr, "allowed", False)]
    denied_results = [tr for tr in (tool_results or []) if not getattr(tr, "allowed", False)]
    citations: List[Citation] = []
    followups: List[str] = []
    detail_sections: List[str] = []
    trace_entries = [_build_tool_trace_entry(tr) for tr in (tool_results or []) if _build_tool_trace_entry(tr)]

    lines: List[str] = ["Маршрутизация Copilot: multi_tool", "", "Итог по вопросу:"]

    for tr in allowed_results:
        retrieved = _select_tool_retrieved(tr, cfg=cfg, effective_top_k=effective_top_k)
        summary_line = _tool_summary_line(tr, retrieved)
        if summary_line:
            lines.append(summary_line)
        body, section_citations, section_followups = _tool_source_only_answer(question, retrieved, "", cfg=cfg, tool_result=tr)
        body = _strip_generic_tool_wrapper(body)
        if body:
            detail_sections.append(f"### {_tool_plan_title(tr)}\n{body}")
        citations.extend(section_citations)
        followups.extend(section_followups)

    if denied_results:
        lines.extend(["", "Недоступные инструменты:"])
        for tr in denied_results:
            entry = _build_tool_trace_entry(tr)
            lines.append(
                f"- {entry.get('tool_name')}: нужен доступ {entry.get('required_permission') or 'NA'} | "
                f"status=forbidden | reason={entry.get('denial_message') or 'NA'}"
            )

    if not allowed_results:
        lines.append("- Нет ни одного доступного инструмента для ответа на этот вопрос.")

    text = "\n".join(lines).strip()
    if detail_sections:
        text = text + "\n\n" + "\n\n".join(detail_sections)
    text = text.rstrip() + "\n\n" + disclaimer

    unique_followups: List[str] = []
    for item in followups:
        value = str(item or "").strip()
        if value and value not in unique_followups:
            unique_followups.append(value)
    return text.strip(), _dedupe_citations(citations), unique_followups[:6], trace_entries



def answer_question_rag(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str,
    question: str,
    web_db_path: Optional[Path] = None,
    use_llm: bool = True,
    llm_model: Optional[str] = None,
    top_k: int = 6,
    user_role: Optional[str] = None,
    user_permissions: Optional[List[str]] = None,
) -> AssistantResponse:
    """Главная функция ассистента. Возвращает ответ с цитатами и версиями."""

    gd = evaluate_guardrails(question)
    fp = build_fact_pack_for_assistant(
        artifacts_root=Path(artifacts_root),
        data_version=str(data_version),
        asof_date=str(asof_date),
        period=str(period),
        web_db_path=web_db_path,
    )

    v = fp.get("versions", {}) or {}
    versions = {
        "data_version": v.get("data_version", str(data_version)),
        "model_version": v.get("model_version", "NA"),
        "report_version": ((fp.get("assistant_knowledge", {}) or {}).get("regular_reports_latest", {}) or {}).get("report_version", "NA"),
        "period": str(period),
        "asof_date": str(asof_date),
    }

    cfg = load_copilot_answer_config()
    answer_cfg = cfg.get("answer", {}) or {}
    llm_cfg = cfg.get("llm", {}) or {}
    tools_cfg = load_copilot_tools_config()
    weekly_plan_cfg = load_weekly_plan_copilot_config()

    query_id = uuid.uuid4().hex
    if is_weekly_plan_request(question, weekly_plan_cfg):
        weekly_plan = build_weekly_plan_from_fact_pack(
            fact_pack=fp,
            question=question,
            week_start=None,
            farm_id=None,
            cfg=weekly_plan_cfg,
        )
        weekly_plan_text = render_weekly_plan_answer(weekly_plan)
        used_llm_flag = False
        weekly_plan_citations: List[Citation] = []
        for cit in list(weekly_plan.get("citations") or []):
            weekly_plan_citations.append(
                Citation(
                    label=str(cit.get("label") or "weekly_plan"),
                    source=str(cit.get("source") or "NA"),
                    data_version=str(cit.get("data_version") or versions.get("data_version") or data_version),
                    period=str(period),
                    asof_date=str(asof_date),
                    run_id=(str(cit.get("run_id")) if cit.get("run_id") else None),
                    report_version=(str(cit.get("report_version")) if cit.get("report_version") else None),
                    section=(str(cit.get("section")) if cit.get("section") else None),
                    table=(str(cit.get("table")) if cit.get("table") else None),
                    metric=(str(cit.get("metric")) if cit.get("metric") else None),
                    fact_id=(str(cit.get("fact_id")) if cit.get("fact_id") else None),
                    deep_link=(str(cit.get("target")) if cit.get("target") else None),
                )
            )
        weekly_plan_citations = _dedupe_citations(weekly_plan_citations)
        text = weekly_plan_text + "\n\n" + gd.disclaimer
        if weekly_plan_citations:
            src_lines = ["\n\nИсточники/версии:"]
            for c in weekly_plan_citations[: int(answer_cfg.get("max_sources", 25))]:
                web_target = build_copilot_web_target({
                    "data_version": c.data_version,
                    "section": c.section or "",
                    "table": c.table or "",
                    "metric": c.metric or "",
                    "run_id": c.run_id or "",
                    "report_version": c.report_version or "",
                    "fact_id": c.fact_id or "",
                })
                src_lines.append(
                    f"- {c.label}: {c.source} | data_version={c.data_version} | run_id={c.run_id or 'NA'} | section={c.section or 'NA'} | table={c.table or 'NA'} | metric={c.metric or 'NA'} | report_version={c.report_version or 'NA'} | target={c.deep_link or 'NA'} | web_target={web_target}"
                )
            text = text.rstrip() + "\n" + "\n".join(src_lines)
        else:
            text = text.rstrip() + "\n\nИсточники/версии: NA"

        _write_assistant_audit_best_effort(
            web_db_path=Path(web_db_path) if web_db_path else None,
            action="assistant.copilot.weekly_plan",
            data_version=str(versions.get("data_version") or data_version),
            run_id=(list(weekly_plan.get("source_run_ids") or [None])[0]),
            object_id=query_id,
            status="OK" if list(weekly_plan.get("action_items") or []) else "MISSING",
            after={
                "question": question,
                "item_count": len(list(weekly_plan.get("action_items") or [])),
                "source_run_ids": list(weekly_plan.get("source_run_ids") or []),
                "source_sections": list(weekly_plan.get("source_sections") or []),
            },
        )
        return AssistantResponse(
            schema="genomeai.ai_assistant_response.v1",
            created_at_utc=_utc_now_iso(),
            query_id=query_id,
            question=question,
            answer=text,
            used_llm=used_llm_flag,
            citations=[asdict(c) for c in weekly_plan_citations],
            versions=versions,
            guardrails=asdict(gd),
            matched_chunk_ids=[],
            suggested_followups=[
                "Нужно ли сохранить weekly plan в draft на утверждение директору?",
                "Показать только пункты по конкретной ферме?",
            ],
            tool_trace=[],
        )

    routed_fp = fp
    tool_result = None
    tool_plan_results: List[Any] = []

    if bool(tools_cfg.get("enabled", True)):
        tool_plan_results = plan_copilot_tools(
            question=question,
            fact_pack=fp,
            user_role=user_role,
            user_permissions=user_permissions,
            cfg=tools_cfg,
        )
        if not tool_plan_results:
            tool_result = execute_copilot_tool(
                question=question,
                fact_pack=fp,
                user_role=user_role,
                user_permissions=user_permissions,
                cfg=tools_cfg,
            )
            routed_fp = tool_result.filtered_fact_pack or fp

    effective_top_k = max(int(top_k), int(answer_cfg.get("max_facts", 5)) + int(answer_cfg.get("max_tables", 3)))
    trace_entries: List[Dict[str, Any]] = []

    if tool_plan_results:
        trace_entries = [_build_tool_trace_entry(tr) for tr in tool_plan_results if _build_tool_trace_entry(tr)]
        _write_assistant_audit_best_effort(
            web_db_path=Path(web_db_path) if web_db_path else None,
            action="assistant.copilot.tool_plan",
            data_version=str(versions.get("data_version") or data_version),
            run_id=None,
            object_id=query_id,
            status="OK" if any(bool(tr.allowed) for tr in tool_plan_results) else "FORBIDDEN",
            after={
                "question": question,
                "tool_trace": trace_entries,
                "user_role": user_role,
            },
            error=None if any(bool(tr.allowed) for tr in tool_plan_results) else "all_tools_forbidden",
        )
    elif tool_result is not None:
        trace_entry = _build_tool_trace_entry(tool_result)
        trace_entries = [trace_entry] if trace_entry else []
        _write_assistant_audit_best_effort(
            web_db_path=Path(web_db_path) if web_db_path else None,
            action="assistant.copilot.tool_route",
            data_version=str(versions.get("data_version") or data_version),
            run_id=None,
            object_id=query_id,
            status="OK" if tool_result.allowed else "FORBIDDEN",
            after={
                "question": question,
                "tool_name": tool_result.decision.tool_name,
                "route_reason": tool_result.decision.route_reason,
                "matched_keywords": list(tool_result.decision.matched_keywords or []),
                "required_permission": tool_result.required_permission,
                "effective_permissions": list(tool_result.effective_permissions or []),
                "visible_section_prefixes": list(tool_result.visible_section_prefixes or []),
                "hidden_section_prefixes": list(tool_result.hidden_section_prefixes or []),
                "query_spec": tool_result.query_spec.as_dict(),
                "user_role": user_role,
            },
            error=None if tool_result.allowed else tool_result.denial_message,
        )
        if not tool_result.allowed:
            answer = (
                f"{tool_result.denial_message}\n\n"
                f"Маршрутизация: {tool_result.decision.tool_name} ({tool_result.decision.label}).\n"
                f"Нужный доступ: {tool_result.required_permission or 'NA'}.\n"
                f"Trace versions: {json.dumps(versions, ensure_ascii=False)}"
            )
            return AssistantResponse(
                schema="genomeai.ai_assistant_response.v1",
                created_at_utc=_utc_now_iso(),
                query_id=query_id,
                question=question,
                answer=answer,
                used_llm=False,
                citations=[],
                versions=versions,
                guardrails=asdict(gd),
                matched_chunk_ids=[],
                suggested_followups=[
                    "Откройте доступ к нужному разделу или смените роль.",
                    "Спросите про другой раздел, который доступен вашей роли.",
                ],
                tool_trace=trace_entries,
            )

    if not gd.allowed:
        answer = gd.disclaimer + "\n\n" + f"Trace versions: {json.dumps(versions, ensure_ascii=False)}"
        return AssistantResponse(
            schema="genomeai.ai_assistant_response.v1",
            created_at_utc=_utc_now_iso(),
            query_id=query_id,
            question=question,
            answer=answer,
            used_llm=False,
            citations=[],
            versions=versions,
            guardrails=asdict(gd),
            matched_chunk_ids=[],
            suggested_followups=["Переформулируйте запрос как вопрос про риск/факты/алерты", "Попросите показать источники по объекту"],
            tool_trace=trace_entries,
        )

    used_llm_flag = False
    citations: List[Citation] = []
    matched_chunk_ids: List[str] = []

    strict_source_only = bool(answer_cfg.get("strict_source_only", True))
    llm_enabled_by_cfg = bool(llm_cfg.get("enabled", True))
    llm_post_validate_enabled = bool(llm_cfg.get("post_validate_enabled", True))
    llm_require_target_links = bool(llm_cfg.get("require_target_links", True))

    text = ""
    followups: List[str] = []
    allowed_corpus = ""

    if tool_plan_results:
        text, citations, followups, trace_entries = _render_multi_tool_answer(
            question=question,
            tool_results=tool_plan_results,
            disclaimer=gd.disclaimer,
            cfg=cfg,
            effective_top_k=effective_top_k,
        )
        all_chunks: List[Chunk] = []
        for tr in tool_plan_results:
            selected = _select_tool_retrieved(tr, cfg=cfg, effective_top_k=effective_top_k)
            all_chunks.extend(selected)
        matched_chunk_ids = [c.chunk_id for c in all_chunks]
        allowed_corpus = "\n".join([c.text for c in all_chunks])
    else:
        chunks = build_chunks_from_fact_pack(routed_fp)
        if tool_result is not None:
            retrieved = list(chunks[: max(int(effective_top_k), len(chunks))])
        else:
            retrieved = retrieve_chunks(question, chunks, top_k=int(effective_top_k))
        has_primary_evidence = any(("[fact]" in (c.text or "") or "[table]" in (c.text or "")) and _is_primary_evidence(c) for c in retrieved)
        if not has_primary_evidence:
            missing_candidates = [c for c in chunks if "[missing_data_request]" in (c.text or "")]
            seen_chunk_ids = {c.chunk_id for c in retrieved}
            for ch in missing_candidates[: int(answer_cfg.get("max_missing_sections", 3))]:
                if ch.chunk_id not in seen_chunk_ids:
                    retrieved.append(ch)
                    seen_chunk_ids.add(ch.chunk_id)
        allowed_corpus = "\n".join([c.text for c in retrieved])
        matched_chunk_ids = [c.chunk_id for c in retrieved]

        if use_llm and llm_enabled_by_cfg and not strict_source_only:
            try:
                from openai import OpenAI  # type: ignore

                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    client = OpenAI(api_key=api_key)
                    chosen_model = llm_model or os.getenv("GENOMEAI_OPENAI_MODEL", "gpt-4o-mini")
                    ctx = "\n\n".join([f"[chunk {i+1}]\n{c.text}" for i, c in enumerate(retrieved[: min(len(retrieved), 6)])])
                    system = (
                        "Вы — ассистент GenomeAI AgroAnimals. "
                        "Вы отвечаете ТОЛЬКО по предоставленным фактам (context). "
                        "Запрещено придумывать цифры/события/названия. "
                        "Каждый числовой факт обязан иметь inline-цитату с fact_id/section/table/metric/run_id/report_version. "
                        "Если факта нет — пишите NA. "
                        "Не ставьте диагнозы и не назначайте лечение — только риск и действия (осмотр/проба/перепроверка)."
                    )
                    user = f"question: {question}\n\nversions: {json.dumps(versions, ensure_ascii=False)}\n\ncontext:\n{ctx}"
                    resp = client.chat.completions.create(
                        model=chosen_model,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                        temperature=0.2,
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    used_llm_flag = True
            except Exception:
                used_llm_flag = False

        if not text:
            text, citations, followups = _tool_source_only_answer(question, retrieved, gd.disclaimer, cfg=cfg, tool_result=tool_result)
        else:
            is_valid_llm_answer, llm_validation_reason = (True, "skipped")
            if llm_post_validate_enabled:
                is_valid_llm_answer, llm_validation_reason = _post_validate_llm_answer(
                    text,
                    retrieved=retrieved,
                    require_target_links=llm_require_target_links,
                )
            if not is_valid_llm_answer:
                _write_assistant_audit_best_effort(
                    web_db_path=Path(web_db_path) if web_db_path else None,
                    action="assistant.copilot.llm_post_validate",
                    data_version=str(versions.get("data_version") or data_version),
                    run_id=next((str(c.run_id) for ch in retrieved for c in (ch.citations or []) if c.run_id), None),
                    object_id=query_id,
                    status="FALLBACK",
                    after={"reason": llm_validation_reason, "question": question, "strict_source_only": strict_source_only},
                    error=llm_validation_reason,
                )
                text, citations, followups = _tool_source_only_answer(question, retrieved, gd.disclaimer, cfg=cfg, tool_result=tool_result)
                used_llm_flag = False
            else:
                followups = ["Хотите сохранить рекомендацию в Decision Log?", "Показать исходные таблицы/алерты по цитатам?"]
                for ch in retrieved:
                    citations.extend(ch.citations)
                citations = _dedupe_citations(citations)

        if citations:
            citations = _dedupe_citations(citations)

        if tool_result is not None and tool_result.allowed:
            tool_trace = _render_tool_trace(tool_result)
            if tool_trace:
                text = tool_trace + "\n\n" + text.lstrip()

    allowed_corpus = allowed_corpus or json.dumps(fp, ensure_ascii=False)[:200_000]
    text = _sanitize_numbers(text, allowed_corpus)

    if citations:
        src_lines = ["\n\nИсточники/версии:"]
        for c in citations[: int(answer_cfg.get("max_sources", 25))]:
            web_target = build_copilot_web_target({
                "data_version": c.data_version,
                "section": c.section or "",
                "table": c.table or "",
                "metric": c.metric or "",
                "run_id": c.run_id or "",
                "report_version": c.report_version or "",
                "fact_id": c.fact_id or "",
            })
            src_lines.append(
                f"- {c.label}: {c.source} | data_version={c.data_version} | run_id={c.run_id or 'NA'} | section={c.section or 'NA'} | table={c.table or 'NA'} | metric={c.metric or 'NA'} | report_version={c.report_version or 'NA'} | target={c.deep_link or 'NA'} | web_target={web_target}"
            )
        text = text.rstrip() + "\n" + "\n".join(src_lines)
    else:
        text = text.rstrip() + "\n\nИсточники/версии: NA"

    _write_assistant_audit_best_effort(
        web_db_path=Path(web_db_path) if web_db_path else None,
        action="assistant.copilot.answer",
        data_version=str(versions.get("data_version") or data_version),
        run_id=next((str(c.run_id) for c in (citations or []) if c.run_id), None),
        object_id=query_id,
        status="OK",
        after={
            "question": question,
            "used_llm": bool(used_llm_flag),
            "matched_chunk_count": len(matched_chunk_ids),
            "citation_count": len(citations or []),
            "strict_source_only": strict_source_only,
            "tool_name": (tool_result.decision.tool_name if tool_result is not None else None),
            "tool_query_spec": (tool_result.query_spec.as_dict() if tool_result is not None else None),
            "tool_trace": trace_entries,
        },
    )

    return AssistantResponse(
        schema="genomeai.ai_assistant_response.v1",
        created_at_utc=_utc_now_iso(),
        query_id=query_id,
        question=question,
        answer=text,
        used_llm=bool(used_llm_flag),
        citations=[asdict(c) for c in (citations or [])],
        versions=versions,
        guardrails=asdict(gd),
        matched_chunk_ids=matched_chunk_ids,
        suggested_followups=followups,
        tool_trace=trace_entries,
    )


def write_assistant_response_artifact(
    *,
    artifacts_root: Path,
    data_version: str,
    response: AssistantResponse,
    report_version: Optional[str] = None,
) -> Path:
    """Записывает ответ ассистента в artifacts (для воспроизводимости)."""
    dv = str(data_version)
    root = Path(artifacts_root) / dv / "assistant" / "responses"
    rv = report_version or response.versions.get("report_version") or "NA"
    out_dir = root / str(rv)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{response.query_id}.json"
    write_json(out_path, asdict(response))
    return out_path
