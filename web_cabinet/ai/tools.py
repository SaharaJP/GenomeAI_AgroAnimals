"""Tool definitions для Anthropic tool use — skeleton для N12."""
from __future__ import annotations

COW_HISTORY_TOOL = {
    "name": "get_cow_history",
    "description": (
        "Получает историю событий по конкретной корове: удои, SCC, лечения, "
        "воспроизводство за указанный период."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cow_id": {"type": "string", "description": "ID коровы"},
            "days_back": {"type": "integer", "description": "Глубина истории в днях", "default": 30},
        },
        "required": ["cow_id"],
    },
}

GROUP_METRICS_TOOL = {
    "name": "get_group_metrics",
    "description": "Получает агрегированные метрики по группе/стаду за период.",
    "input_schema": {
        "type": "object",
        "properties": {
            "group_id": {"type": "string", "description": "ID группы, или 'all' для всего стада"},
            "metric": {
                "type": "string",
                "enum": ["milk_yield", "scc", "reproduction", "health"],
                "description": "Тип метрики",
            },
            "days_back": {"type": "integer", "default": 7},
        },
        "required": ["metric"],
    },
}

EVENT_SEARCH_TOOL = {
    "name": "search_events",
    "description": "Ищет события по ферме: болезни, лечения, осеменения, отёлы, выбраковки.",
    "input_schema": {
        "type": "object",
        "properties": {
            "event_type": {
                "type": "string",
                "enum": ["mastitis", "treatment", "insemination", "calving", "culling", "scc_spike", "all"],
            },
            "days_back": {"type": "integer", "default": 14},
            "cow_id": {"type": "string", "description": "Опционально: фильтр по корове"},
        },
        "required": ["event_type"],
    },
}

TREATMENT_TOOL = {
    "name": "get_treatments",
    "description": "Получает список текущих и завершённых лечений.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["active", "completed", "all"], "default": "active"},
            "days_back": {"type": "integer", "default": 30},
        },
    },
}

REPRODUCTION_TOOL = {
    "name": "get_reproduction_status",
    "description": "Получает статус воспроизводства: коровы в охоте, стельные, ожидающие осеменения.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["in_heat", "pregnant", "open", "all"],
                "default": "all",
            },
        },
    },
}

MILK_QUALITY_TOOL = {
    "name": "get_milk_quality",
    "description": "Получает показатели качества молока: SCC, жир, белок, бактериальная обсеменённость.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days_back": {"type": "integer", "default": 7},
            "level": {"type": "string", "enum": ["herd", "group", "cow"], "default": "herd"},
            "id": {"type": "string", "description": "ID группы или коровы (при level != herd)"},
        },
    },
}

ECONOMICS_TOOL = {
    "name": "get_economics",
    "description": "Получает экономические показатели: выручка, затраты, маржа, прогноз.",
    "input_schema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["day", "week", "month"], "default": "week"},
        },
    },
}

ALL_TOOLS = [
    COW_HISTORY_TOOL,
    GROUP_METRICS_TOOL,
    EVENT_SEARCH_TOOL,
    TREATMENT_TOOL,
    REPRODUCTION_TOOL,
    MILK_QUALITY_TOOL,
    ECONOMICS_TOOL,
]
