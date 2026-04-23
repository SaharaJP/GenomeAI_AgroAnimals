"""POST /api/ai/ask-farm — интерактивный Q&A с фермером (MVP-N13-b).

Принимает вопрос, строит farm context, вызывает Claude, извлекает [evidence: id]
из ответа и верифицирует каждый ID против known event IDs из контекста.
Непроверенные ссылки помечаются verified=False и описанием «⚠ unverified: <id>».
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException

from ..models import AskFarmEvidence, AskFarmRequest, AskFarmResponse

logger = logging.getLogger("genomeai.ai.endpoint.ask_farm")
router = APIRouter()

_EVIDENCE_RE = re.compile(r"\[evidence:\s*([\w_\-]+)\]", re.IGNORECASE)


def _extract_known_event_ids(ctx: dict) -> set[str]:
    """Извлекает все known event_id из farm context dict."""
    ids: set[str] = set()
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


def parse_evidence_from_response(answer: str, known_ids: set[str]) -> list[AskFarmEvidence]:
    """Парсит [evidence: id] из ответа AI и верифицирует против known_ids.

    Возвращает дедуплицированный список. Непроверенные: verified=False,
    description начинается с «⚠ unverified: <id>».
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


@router.post("/ask-farm", response_model=AskFarmResponse)
async def ask_farm(request: AskFarmRequest) -> AskFarmResponse:
    """Задай вопрос по ферме — получи ответ с верифицированными evidence chips."""
    from ..client import get_client
    from ..config import get_ai_settings
    from ..context import build_farm_context
    from ..prompts.ask_farm import ASK_FARM_SYSTEM, build_ask_farm_message

    settings = get_ai_settings()

    farm_ctx: dict = {}
    farm_ctx_text = ""
    known_event_ids: set[str] = set()

    if request.include_context:
        try:
            farm_ctx = build_farm_context(request.farm_id)
            farm_ctx_text = json.dumps(farm_ctx, ensure_ascii=False, default=str)
            known_event_ids = _extract_known_event_ids(farm_ctx)
        except Exception as exc:
            logger.warning(f"farm_context build failed farm={request.farm_id}: {exc}")

    user_message = build_ask_farm_message(request.question)

    if settings.GENOMEAI_AI_DEMO_MODE or not settings.ANTHROPIC_API_KEY:
        answer = _demo_answer(request.question, request.farm_id, known_event_ids)
        evidences = parse_evidence_from_response(answer, known_event_ids)
        unverified = sum(1 for e in evidences if not e.verified)
        return AskFarmResponse(
            answer=answer,
            evidence=evidences,
            model="demo",
            unverified_count=unverified,
        )

    client = get_client()
    try:
        result = await client.agenerate(
            user_message,
            system_prompt=ASK_FARM_SYSTEM,
            farm_context=farm_ctx_text or None,
            task_type="ask_farm",
            max_tokens=1024,
            user_id=request.user_id,
        )
    except Exception as exc:
        logger.error(f"ask_farm LLM call failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"llm_error: {exc}") from exc

    evidences = parse_evidence_from_response(result.content, known_event_ids)
    unverified = sum(1 for e in evidences if not e.verified)

    if unverified:
        logger.warning(json.dumps({
            "event": "unverified_evidence_detected",
            "farm_id": request.farm_id,
            "user_id": request.user_id,
            "unverified_ids": [e.event_id for e in evidences if not e.verified],
        }))

    return AskFarmResponse(
        answer=result.content,
        evidence=evidences,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_hit=result.cache_hit,
        latency_ms=result.latency_ms,
        unverified_count=unverified,
    )


def _demo_answer(question: str, farm_id: str, known_ids: set[str]) -> str:
    """Demo ответ для offline/demo режима.

    Если вопрос содержит числовой ID коровы, которого нет в known animal IDs
    из контекста — сообщаем честно. Иначе возвращаем canned demo с evidence.
    """
    q_lower = question.lower()

    # Ищем числовые ID коров (4–6 цифр) в вопросе
    candidate_ids = re.findall(r"\b(\d{4,6})\b", question)
    # Проверяем: есть ли в known_ids хоть одно событие, связанное с этим cow_id
    if candidate_ids:
        found_any = any(
            any(cid in eid for eid in known_ids)
            for cid in candidate_ids
        )
        if not found_any:
            return (
                f"Животное с ID {candidate_ids[0]} не найдено в данных фермы {farm_id}. "
                "Проверь идентификатор или обратись к оператору для уточнения."
            )

    return (
        f"Demo-режим — ферма {farm_id}. "
        "SCC у коровы 4821 (Звёздочка) растёт: 450 тыс. за последние 9 дней "
        "[evidence: event_4821_scc_spike]. "
        "Сегодня зафиксировано 8 охот [evidence: event_heat_batch_20260421]. "
        "Рекомендую: немедленно проверь корову 4821 на субклинический мастит."
    )
