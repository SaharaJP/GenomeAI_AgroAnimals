"""POST /api/ai/morning-brief — ежедневный брифинг ИИ-помощника."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _BaseModel

from ..cache import get_cache
from ..client import get_client
from ..config import get_ai_settings
from ..models import MorningBrief, MorningBriefRequest, OvernightChange, TodayAction
from ..prompts.morning_brief import MORNING_BRIEF_SYSTEM, build_morning_brief_message

logger = logging.getLogger("genomeai.ai.endpoint.morning_brief")
router = APIRouter()

_SEEDED_PATH = Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "morning_briefs_seeded.json"
_CACHE_TTL_SECONDS = 86400  # 24ч — брифинг валиден весь день


# ---------------------------------------------------------------------------
# public helper (used by cron)
# ---------------------------------------------------------------------------

async def _generate_brief(farm_id: str, force_regenerate: bool = False) -> MorningBrief:
    settings = get_ai_settings()
    today = date.today()
    cache = get_cache()
    cache_key = cache.make_key("morning_brief", {"farm_id": farm_id, "date": today.isoformat()})

    if not force_regenerate:
        cached = cache.get(cache_key)
        if cached:
            try:
                return MorningBrief(**json.loads(cached))
            except Exception:
                pass

    if settings.GENOMEAI_AI_DEMO_MODE:
        brief = _load_seeded_brief(farm_id, today)
        cache.set(cache_key, brief.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
        return brief

    # Build farm context (period_days=1 — только последние 24 часа)
    from ..context import build_farm_context
    ctx = build_farm_context(farm_id, period_days=1)

    user_message = build_morning_brief_message(ctx, today.isoformat())
    client = get_client()
    resp = client.generate(
        user_message,
        system_prompt=MORNING_BRIEF_SYSTEM,
        task_type="morning_brief",
        max_tokens=1500,
        temperature=0.3,
    )

    brief = _parse_response(resp.content, farm_id, today, resp.model, resp.input_tokens, resp.output_tokens)
    _save_to_db(brief)
    cache.set(cache_key, brief.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
    return brief


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------

@router.post("/morning-brief", response_model=MorningBrief)
async def generate_morning_brief(req: MorningBriefRequest) -> MorningBrief:
    """Генерирует или возвращает кэшированный утренний брифинг для фермы."""
    try:
        return await _generate_brief(farm_id=req.farm_id, force_regenerate=req.force_regenerate)
    except Exception as exc:
        logger.error(f"morning_brief error farm={req.farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"morning_brief_failed: {exc}") from exc


@router.get("/morning-brief/today", response_model=MorningBrief)
async def get_today_morning_brief(farm_id: str = "demo-farm-v1") -> MorningBrief:
    """GET-версия для dashboard — возвращает брифинг сегодня (генерирует при отсутствии)."""
    try:
        return await _generate_brief(farm_id=farm_id, force_regenerate=False)
    except Exception as exc:
        logger.error(f"morning_brief today error farm={farm_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"morning_brief_failed: {exc}") from exc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_seeded_brief(farm_id: str, today: date) -> MorningBrief:
    """Загружает seeded брифинг из demo-данных."""
    try:
        if _SEEDED_PATH.exists():
            records = json.loads(_SEEDED_PATH.read_text(encoding="utf-8"))
            if records:
                rec = records[0]
                return _brief_from_seeded(rec, farm_id, today)
    except Exception as exc:
        logger.warning(f"seeded brief load failed: {exc}")
    return _fallback_brief(farm_id, today)


def _brief_from_seeded(rec: dict, farm_id: str, today: date) -> MorningBrief:
    """Преобразует seeded запись в MorningBrief."""
    overnight = []
    for h in rec.get("overnight_changes", rec.get("highlights", [])):
        if isinstance(h, dict):
            overnight.append(OvernightChange(**h))
        else:
            overnight.append(OvernightChange(text=str(h), evidence_id=None))
    actions = [
        TodayAction(**a) if isinstance(a, dict) else TodayAction(
            action=a, priority="medium", due=None, role="operator"
        )
        for a in rec.get("today_actions", [])
    ]
    return MorningBrief(
        brief_id=rec.get("brief_id", f"mb_seeded_{today.isoformat()}"),
        farm_id=farm_id,
        generated_at_utc=datetime.fromisoformat(
            rec.get("generated_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
        ).replace(tzinfo=None),
        date=today,
        headline=rec.get("headline", "Демо-брифинг"),
        main_takeaway=rec.get("main_takeaway", "; ".join(rec.get("highlights", [])[:2])),
        overnight_changes=overnight,
        today_actions=actions,
        notes=rec.get("notes", []),
        generation_model="demo-seeded",
        generation_tokens={"input": 0, "output": 0},
    )


def _fallback_brief(farm_id: str, today: date) -> MorningBrief:
    return MorningBrief(
        farm_id=farm_id,
        date=today,
        headline="Спокойное утро — плановая работа",
        main_takeaway="Данные фермы недоступны. Брифинг в demo-режиме без фактических событий.",
        overnight_changes=[],
        today_actions=[
            TodayAction(action="Проверить доступность данных фермы", priority="medium", due=None, role="operator")
        ],
        notes=["Demo-режим: реальные данные не подключены"],
        generation_model="demo-fallback",
        generation_tokens={"input": 0, "output": 0},
    )


def _parse_response(
    content: str,
    farm_id: str,
    today: date,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> MorningBrief:
    """Парсит JSON-ответ LLM в MorningBrief."""
    raw = content.strip()
    # Strip possible markdown fence
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\ncontent={raw[:500]}") from exc

    overnight = [
        OvernightChange(**ch) if isinstance(ch, dict) else OvernightChange(text=str(ch))
        for ch in data.get("overnight_changes", [])
    ]
    actions = []
    for a in data.get("today_actions", []):
        if isinstance(a, dict):
            actions.append(TodayAction(
                action=a.get("action", ""),
                priority=a.get("priority", "medium"),
                due=a.get("due"),
                role=a.get("role", "operator"),
            ))

    return MorningBrief(
        farm_id=farm_id,
        date=today,
        headline=data.get("headline", "Брифинг готов"),
        main_takeaway=data.get("main_takeaway", ""),
        overnight_changes=overnight,
        today_actions=actions,
        notes=data.get("notes", []),
        generation_model=model,
        generation_tokens={"input": input_tokens, "output": output_tokens},
    )


# ---------------------------------------------------------------------------
# Approve endpoint
# ---------------------------------------------------------------------------

_approve_logger = logging.getLogger("genomeai.ai.endpoint.morning_brief.approve")

_PRIORITY_MAP = {"high": 1, "medium": 2, "low": 3}


class _ApproveAction(_BaseModel):
    action: str
    priority: str  # 'high' | 'medium' | 'low'
    due: Optional[str]
    role: str  # 'vet' | 'zootech' | 'operator' | 'director'


class ApproveBriefRequest(_BaseModel):
    farm_id: str
    actions: list[_ApproveAction]


class ApproveBriefResponse(_BaseModel):
    approved: bool
    tasks_created: int


def _create_tasks_for_actions(actions: list, *, brief_id: str, farm_id: str) -> int:
    """Create worklist tasks for each approved action. Returns count created."""
    try:
        from core.infra.postgres_compat import connect_postgres_compat
        from core.workflow.tasks import TaskCreate, create_task
    except ImportError:
        _approve_logger.warning("task creation unavailable: core.workflow not importable")
        return 0

    conn = connect_postgres_compat()
    created = 0
    try:
        for act in actions:
            t = TaskCreate(
                task_type="morning_brief_action",
                title=act.action,
                priority=_PRIORITY_MAP.get(act.priority, 2),
                assignee_team=None,  # role stored in why dict; teams catalog uses different keys
                due_at=act.due,
                why={
                    "source": "morning_brief",
                    "brief_id": brief_id,
                    "farm_id": farm_id,
                    "role": act.role,
                },
            )
            # TODO: resolve tenant_id from request context for multi-tenant support (MVP: default)
            create_task(conn, tenant_id="default", t=t)
            created += 1
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return created


@router.post("/morning-brief/{brief_id}/approve", response_model=ApproveBriefResponse)
async def approve_morning_brief(brief_id: str, body: ApproveBriefRequest) -> ApproveBriefResponse:
    """Согласовать брифинг: поставить задачи на специалистов и разблокировать PDF."""
    tasks_created = 0
    try:
        tasks_created = _create_tasks_for_actions(
            body.actions, brief_id=brief_id, farm_id=body.farm_id
        )
    except Exception as exc:
        _approve_logger.warning("approve: task creation failed (graceful): %s", exc)
    return ApproveBriefResponse(approved=True, tasks_created=tasks_created)


def _save_to_db(brief: MorningBrief) -> None:
    """Сохраняет брифинг в Postgres. Gracefully skips if DB unavailable."""
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return
    try:
        import psycopg2  # type: ignore[import-untyped]
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO morning_briefs
              (brief_id, farm_id, brief_date, generated_at_utc,
               headline, main_takeaway, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (brief_id) DO NOTHING
            """,
            (
                brief.brief_id,
                brief.farm_id,
                brief.date.isoformat(),
                brief.generated_at_utc.isoformat(),
                brief.headline,
                brief.main_takeaway,
                brief.model_dump_json(),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"morning_brief saved to db brief_id={brief.brief_id}")
    except Exception as exc:
        logger.warning(f"morning_brief db save skipped: {exc}")
