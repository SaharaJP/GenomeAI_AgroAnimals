"""SSE endpoint POST /api/ai/ask-farm — интерактивный Q&A с фермой.

Evidence IDs верифицируются против known event IDs из farm context (MVP-N12/N13).
Непроверенные ссылки помечаются verified=False в SSE evidence event.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import get_ai_settings
from ..guardrails import GuardrailError, input_sanitize, rate_limit_check
from ..models import AskFarmEvidence

logger = logging.getLogger("genomeai.ai.ask_farm")

router = APIRouter()

_EVIDENCE_RE = re.compile(r"\[evidence:\s*([\w_\-]+)\]", re.IGNORECASE)

_PRESET_QUESTION_MAP = {
    "почему упал удой у звёздочки": "why_star_milk_drop",
    "кого рекомендуется выбраковать": "which_to_cull",
    "какие коровы в охоте сегодня": "cows_in_heat_today",
}

_PRESET_DATA: Optional[dict] = None


def _load_preset_data() -> dict:
    global _PRESET_DATA
    if _PRESET_DATA is None:
        preset_path = (
            Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "preset_ai_answers.json"
        )
        try:
            _PRESET_DATA = json.loads(preset_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Не удалось загрузить preset_ai_answers.json: {exc}")
            _PRESET_DATA = {}
    return _PRESET_DATA


def _find_preset_key(question: str) -> Optional[str]:
    q_lower = question.lower().strip().rstrip("?")
    for pattern, key in _PRESET_QUESTION_MAP.items():
        if pattern in q_lower:
            return key
    return None


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# Структурные ключи farm context — валидные источники для [evidence: ...]
_CONTEXT_KEY_LABELS: dict[str, str] = {
    "farm_summary":    "Сводка фермы",
    "today_kpi":       "KPI сегодня",
    "period_trends":   "Тренды за период",
    "active_insights": "Активные инсайты",
    "recent_events":   "Недавние события",
    "attention_cows":  "Коровы под наблюдением",
    "groups_summary":  "Сводка по группам",
}


def _extract_known_event_ids(ctx: dict) -> set[str]:
    """Извлекает все known event_id из farm context dict.

    Включает структурные ключи верхнего уровня (farm_summary, today_kpi и т.д.)
    как валидные anchors — Claude вправе на них ссылаться.
    """
    ids: set[str] = set()
    # Структурные ключи context всегда валидны
    ids.update(_CONTEXT_KEY_LABELS.keys())
    for event in ctx.get("recent_events", []):
        eid = str(event.get("evidence_id", "")).strip()
        if eid and eid != "nan":
            ids.add(eid)
    for profile in ctx.get("full_profiles", {}).values():
        for he in profile.get("health_events", []):
            eid = str(he.get("event_id", "")).strip()
            if eid and eid != "nan":
                ids.add(eid)
        for tr in profile.get("treatments", []):
            eid = str(tr.get("treatment_id", "")).strip()
            if eid and eid != "nan":
                ids.add(eid)
    return ids


def _build_context_key_description(eid: str, farm_ctx: dict) -> str:
    """Строит читаемое описание для структурного ключа farm context."""
    if eid == "farm_summary":
        fs = farm_ctx.get("farm_summary", {})
        total = fs.get("total_cows", "?")
        name = fs.get("name", "")
        as_of = fs.get("date_as_of", "")
        parts = [f"Поголовье: {total} гол."]
        if name:
            parts.append(f"Ферма: {name}")
        if as_of:
            parts.append(f"На дату: {as_of}")
        return " · ".join(parts)
    if eid == "today_kpi":
        kpi = farm_ctx.get("today_kpi", {})
        parts = []
        if "avg_milk_kg" in kpi:
            parts.append(f"Надой: {kpi['avg_milk_kg']} кг")
        if "scc_avg" in kpi:
            parts.append(f"СКК: {kpi['scc_avg']}")
        return " · ".join(parts) or "KPI текущего дня"
    return _CONTEXT_KEY_LABELS.get(eid, eid.replace("_", " "))


def parse_evidence_from_response(answer: str, known_ids: set[str]) -> list[AskFarmEvidence]:
    """Парсит [evidence: id] из ответа AI и верифицирует против known_ids.

    Дедуплицирует. Непроверенные: verified=False, description = «⚠ unverified: <id>».
    """
    seen: set[str] = set()
    result: list[AskFarmEvidence] = []
    for eid in _EVIDENCE_RE.findall(answer):
        if eid in seen:
            continue
        seen.add(eid)
        if eid in known_ids:
            result.append(AskFarmEvidence(event_id=eid, description=eid, verified=True))
        else:
            result.append(AskFarmEvidence(
                event_id=eid,
                description=f"⚠ unverified: {eid}",
                verified=False,
            ))
    return result


async def _stream_preset(preset: dict, session_id: str) -> AsyncIterator[str]:
    """Стримит preset-ответ пословно, имитируя токен-стриминг."""
    model = preset.get("model", "claude-sonnet-4-6")
    answer: str = preset.get("answer", "")
    evidence_items: list[dict] = preset.get("evidence", [])

    yield _sse_event("start", {"session_id": session_id, "model": model})

    words = answer.split(" ")
    collected = ""

    for i, word in enumerate(words):
        token = word if i == 0 else " " + word
        yield _sse_event("token", {"text": token})
        collected += token

        await asyncio.sleep(0.02)

        for match in _EVIDENCE_RE.finditer(collected):
            ev_id = match.group(1)
            ev_data = next((e for e in evidence_items if e.get("id") == ev_id), None)
            if ev_data:
                yield _sse_event("evidence", {
                    "type": ev_data.get("type", "event"),
                    "id": ev_data["id"],
                    "name": ev_data.get("name", ev_id),
                    "description": ev_data.get("description", ""),
                    "cow_id": ev_data.get("cow_id"),
                    "cow_name": ev_data.get("cow_name"),
                    "verified": True,
                })
        collected = _EVIDENCE_RE.sub("", collected)

    approx_output = len(answer) // 4
    yield _sse_event("done", {
        "total_tokens": {"input": 1200, "output": approx_output},
        "evidence_ids": [e["id"] for e in evidence_items],
        "validated_evidence": True,
        "demo_cached": True,
    })


async def _stream_live(
    question: str,
    session_id: str,
    user_id: str,
    farm_id: str,
    messages_history: list[dict],
) -> AsyncIterator[str]:
    """Стримит живой ответ от Claude, верифицирует evidence против farm context."""
    from ..client import get_client
    from ..context import build_farm_context
    from ..prompts.ask_farm import ASK_FARM_SYSTEM, build_ask_farm_message
    from ..session_memory import get_session_memory

    settings = get_ai_settings()
    model = settings.GENOMEAI_AI_DEFAULT_MODEL

    yield _sse_event("start", {"session_id": session_id, "model": model})

    farm_ctx: dict = {}
    farm_ctx_text = ""
    known_event_ids: set[str] = set()
    try:
        farm_ctx = build_farm_context(farm_id)
        farm_ctx_text = json.dumps(farm_ctx, ensure_ascii=False, default=str)
        known_event_ids = _extract_known_event_ids(farm_ctx)
    except Exception as exc:
        logger.warning(f"farm_context build failed farm={farm_id}: {exc}")

    user_message = build_ask_farm_message(question)

    history_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in messages_history
    ]

    client = get_client()
    full_text = ""
    input_tokens = 0
    output_tokens = 0

    try:
        async for chunk in client.astream(
            user_message=user_message,
            system_prompt=ASK_FARM_SYSTEM,
            farm_context=farm_ctx_text or None,
            task_type="ask_farm",
            user_id=user_id,
        ):
            full_text += chunk
            yield _sse_event("token", {"text": chunk})

        evidences = parse_evidence_from_response(full_text, known_event_ids)
        for ev in evidences:
            is_ctx_key = ev.event_id in _CONTEXT_KEY_LABELS
            name = _CONTEXT_KEY_LABELS.get(ev.event_id, ev.event_id.replace("_", " "))
            description = (
                _build_context_key_description(ev.event_id, farm_ctx)
                if is_ctx_key
                else ev.description
            )
            ev_type = "farm_context" if is_ctx_key else "event"
            yield _sse_event("evidence", {
                "type": ev_type,
                "id": ev.event_id,
                "name": name,
                "description": description,
                "verified": ev.verified,
            })

        unverified = sum(1 for e in evidences if not e.verified)
        if unverified:
            logger.warning(json.dumps({
                "event": "unverified_evidence_detected",
                "farm_id": farm_id,
                "user_id": user_id,
                "unverified_ids": [e.event_id for e in evidences if not e.verified],
            }))

        output_tokens = len(full_text) // 4

        try:
            mem = get_session_memory()
            mem.append(session_id, "user", question)
            mem.append(session_id, "assistant", full_text)
        except Exception as exc:
            logger.warning(f"session_memory.append error: {exc}")

        yield _sse_event("done", {
            "total_tokens": {"input": input_tokens, "output": output_tokens},
            "evidence_ids": [e.event_id for e in evidences],
            "validated_evidence": unverified == 0,
            "unverified_count": unverified,
        })

    except Exception as exc:
        logger.error(f"ask_farm live stream error: {exc}")
        yield _sse_event("error", {"message": "Ошибка AI-сервиса. Попробуйте позже."})


class AskFarmStreamRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    farm_id: str = "demo-farm-v1"
    language: str = "ru"
    session_id: Optional[str] = None
    user_id: str = "anonymous"


@router.post("/ask-farm")
async def ask_farm_stream(body: AskFarmStreamRequest, request: Request) -> StreamingResponse:
    """POST /api/ai/ask-farm — SSE streaming Q&A endpoint."""
    settings = get_ai_settings()
    session_id = body.session_id or str(uuid.uuid4())
    user_id = body.user_id

    try:
        question = input_sanitize(body.question)
    except GuardrailError as exc:
        async def _error_stream():
            yield _sse_event("error", {"message": str(exc)})
        return StreamingResponse(_error_stream(), media_type="text/event-stream")

    try:
        from ..cache import get_cache
        cache = get_cache()
        if cache.ping():
            rate_limit_check(
                user_id=user_id,
                endpoint="ask_farm",
                per_min=settings.GENOMEAI_AI_RATE_LIMIT_PER_MIN,
                per_hour=settings.GENOMEAI_AI_RATE_LIMIT_PER_HOUR,
                redis_client=cache._get_client(),
            )
    except GuardrailError as exc:
        async def _rl_error():
            yield _sse_event("error", {"message": str(exc)})
        return StreamingResponse(_rl_error(), media_type="text/event-stream")
    except Exception:
        pass

    if settings.GENOMEAI_AI_DEMO_MODE:
        preset_key = _find_preset_key(question)
        if preset_key:
            preset_data = _load_preset_data()
            preset = preset_data.get(preset_key)
            if preset:
                logger.info(json.dumps({
                    "event": "ask_farm_preset_hit",
                    "preset_key": preset_key,
                    "session_id": session_id,
                }))
                return StreamingResponse(
                    _stream_preset(preset, session_id),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )

    if not settings.is_configured:
        async def _not_configured():
            yield _sse_event("error", {"message": "AI-сервис не настроен. Установите ANTHROPIC_API_KEY."})
        return StreamingResponse(_not_configured(), media_type="text/event-stream")

    messages_history: list[dict] = []
    try:
        from ..session_memory import get_session_memory
        messages_history = get_session_memory().load(session_id)
    except Exception:
        pass

    logger.info(json.dumps({
        "event": "ask_farm_live",
        "user_id": user_id,
        "session_id": session_id,
        "question_len": len(question),
    }))

    return StreamingResponse(
        _stream_live(question, session_id, user_id, body.farm_id, messages_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
