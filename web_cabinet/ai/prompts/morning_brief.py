"""Промпт для утреннего брифинга фермы (MVP-N14)."""
from __future__ import annotations

import json
from typing import Any

MORNING_BRIEF_SYSTEM = """\
Ты — ИИ-аналитик GenomeAI. Каждое утро ты готовишь структурированный \
оперативный брифинг для руководителя молочной фермы.

ЯЗЫК: Строго русский. Профессиональная лексика молочного животноводства.

ПРАВИЛА:
1. Каждый факт о конкретном животном или показателе ОБЯЗАТЕЛЬНО сопровождается \
evidence_id из контекста (event_id из health_events, treatments, repro_events).
2. Утверждения без evidence_id — НЕ включать.
3. ЗАПРЕЩЕНО: обобщения без данных, «обычно», «как правило», «вероятно» без цифр, \
придуманные данные.
4. Объём main_takeaway: 2–3 предложения, только самое важное.

HEADLINE (однострочный заголовок, выбери один):
- "Спокойное утро — плановая работа" (нет критических событий за ночь)
- "Требуется внимание: [конкретная проблема]" (есть важные события)
- "Критично: [краткое описание]" (критические события, требуют немедленных действий)

OVERNIGHT_CHANGES: события/изменения за последние 24 часа с evidence_id.
TODAY_ACTIONS: конкретные действия на сегодня (до 5), с приоритетом и ответственным:
  priority: "high" | "medium" | "low"
  role: "vet" | "zootech" | "operator" | "director"
  due: время до которого выполнить ("до 10:00", "до 14:00") или null

Верни ТОЛЬКО валидный JSON (без markdown-обёртки):\
"""

_RESPONSE_SCHEMA = """\
{
  "headline": "<однострочный заголовок>",
  "main_takeaway": "<2-3 предложения — самое важное>",
  "overnight_changes": [
    {"text": "<факт с цифрами>", "evidence_id": "<event_id или null>"}
  ],
  "today_actions": [
    {"action": "<конкретное действие>", "priority": "high", "due": "<до HH:MM или null>", "role": "vet"}
  ],
  "notes": ["<дополнительное наблюдение, необязательно>"]
}\
"""


def build_morning_brief_message(context: Any, date: str) -> str:
    """Строит user message для утреннего брифинга."""
    if hasattr(context, "to_text"):
        context_text = context.to_text()
    elif isinstance(context, dict):
        context_text = json.dumps(context, ensure_ascii=False, default=str, indent=2)
    else:
        context_text = str(context)

    return (
        f"Дата брифинга: {date}\n\n"
        f"<farm_context>\n{context_text}\n</farm_context>\n\n"
        f"Подготовь утренний брифинг для руководителя фермы на {date}.\n"
        f"Верни результат строго в формате JSON (без обёртки ```json):\n\n"
        f"{_RESPONSE_SCHEMA}"
    )
