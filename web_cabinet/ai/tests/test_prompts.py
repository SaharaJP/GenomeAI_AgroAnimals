"""Тесты промптов: evidence grounding, русский язык, структура."""
from __future__ import annotations

import pytest

from web_cabinet.ai.prompts import (
    ASK_FARM_SYSTEM,
    MORNING_BRIEF_SYSTEM,
    WEEKLY_BRIEF_SYSTEM,
    INSIGHT_SCANNER_SYSTEM,
    IMPACT_NARRATIVE_SYSTEM,
    INSIGHT_NARRATIVE_SYSTEM,
    build_ask_farm_message,
    build_morning_brief_message,
    build_weekly_brief_message,
    build_insight_scanner_message,
    build_impact_narrative_message,
    build_insight_narrative_message,
)
from web_cabinet.ai.context import FarmContext, build_demo_farm_context

ALL_SYSTEM_PROMPTS = [
    ("ASK_FARM_SYSTEM", ASK_FARM_SYSTEM),
    ("MORNING_BRIEF_SYSTEM", MORNING_BRIEF_SYSTEM),
    ("WEEKLY_BRIEF_SYSTEM", WEEKLY_BRIEF_SYSTEM),
    ("INSIGHT_SCANNER_SYSTEM", INSIGHT_SCANNER_SYSTEM),
    ("IMPACT_NARRATIVE_SYSTEM", IMPACT_NARRATIVE_SYSTEM),
    ("INSIGHT_NARRATIVE_SYSTEM", INSIGHT_NARRATIVE_SYSTEM),
]


class TestSystemPromptRequirements:
    @pytest.mark.parametrize("name,prompt", ALL_SYSTEM_PROMPTS)
    def test_requires_russian_language(self, name, prompt):
        has_russian_instruction = (
            "русск" in prompt.lower()
            or "русский" in prompt.lower()
            or "ЯЗЫК" in prompt
            or "язык" in prompt.lower()
        )
        assert has_russian_instruction, (
            f"{name}: промпт должен содержать инструкцию отвечать на русском языке"
        )

    @pytest.mark.parametrize("name,prompt", ALL_SYSTEM_PROMPTS)
    def test_requires_evidence_grounding(self, name, prompt):
        has_evidence_instruction = (
            "evidence" in prompt.lower()
            or "[evidence:" in prompt
            or "evidence_id" in prompt.lower()
        )
        assert has_evidence_instruction, (
            f"{name}: промпт должен требовать evidence grounding"
        )

    @pytest.mark.parametrize("name,prompt", ALL_SYSTEM_PROMPTS)
    def test_prompt_not_empty(self, name, prompt):
        assert len(prompt.strip()) > 100, f"{name}: промпт слишком короткий"

    @pytest.mark.parametrize("name,prompt", ALL_SYSTEM_PROMPTS)
    def test_no_hallucination_instruction(self, name, prompt):
        anti_hallucination_keywords = [
            "не придумывай",
            "запрещено",
            "только с данными",
            "без evidence",
            "не включать",
            "не оценивай",
        ]
        prompt_lower = prompt.lower()
        has_anti_hallucination = any(kw in prompt_lower for kw in anti_hallucination_keywords)
        assert has_anti_hallucination, (
            f"{name}: промпт должен явно запрещать галлюцинации"
        )


class TestBuildUserMessages:
    def _demo_ctx(self) -> FarmContext:
        return build_demo_farm_context()

    def test_ask_farm_message_includes_question(self):
        msg = build_ask_farm_message("Какой SCC у Звёздочки?")
        assert "Какой SCC у Звёздочки?" in msg

    def test_ask_farm_message_with_context(self):
        ctx = self._demo_ctx()
        msg = build_ask_farm_message("Тест вопрос", context=ctx)
        assert "farm_context" in msg
        assert "demo-farm-v1" in msg

    def test_morning_brief_includes_date(self):
        ctx = self._demo_ctx()
        msg = build_morning_brief_message(ctx, "2026-04-21")
        assert "2026-04-21" in msg
        assert "JSON" in msg

    def test_weekly_brief_includes_period(self):
        ctx = self._demo_ctx()
        msg = build_weekly_brief_message(ctx, "2026-04-14", "2026-04-20")
        assert "2026-04-14" in msg
        assert "2026-04-20" in msg

    def test_insight_scanner_includes_farm_context(self):
        ctx = self._demo_ctx()
        msg = build_insight_scanner_message(ctx)
        assert "farm_context" in msg

    def test_impact_narrative_includes_event(self):
        ctx = self._demo_ctx()
        event = {"event_id": "event_001", "type": "mastitis"}
        msg = build_impact_narrative_message(event, ctx)
        assert "event_001" in msg
        assert "farm_context" in msg

    def test_insight_narrative_includes_insight(self):
        ctx = self._demo_ctx()
        insight = {"id": "insight_001", "title": "SCC растёт"}
        msg = build_insight_narrative_message(insight, ctx)
        assert "insight_001" in msg
        assert "farm_context" in msg


class TestFarmContextText:
    def test_demo_context_has_farm_id(self):
        ctx = build_demo_farm_context()
        text = ctx.to_text()
        assert "demo-farm-v1" in text

    def test_demo_context_has_kpi(self):
        ctx = build_demo_farm_context()
        text = ctx.to_text()
        assert "KPI" in text or "kpi" in text.lower() or "28.4" in text

    def test_demo_context_truncates_at_max_chars(self):
        ctx = build_demo_farm_context()
        text = ctx.to_text(max_chars=50)
        assert len(text) <= 60

    def test_empty_context_to_text(self):
        ctx = FarmContext(farm_id="test-farm")
        text = ctx.to_text()
        assert "test-farm" in text
