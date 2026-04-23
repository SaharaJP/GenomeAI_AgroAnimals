"""Тесты для MVP-N17 Weekly Brief Generator.

Покрывает:
- Pydantic-валидацию WeeklyBrief и WeeklyBriefRequest
- Парсинг JSON-ответа LLM (_parse_response)
- Demo-режим: загрузку seeded briefs с точным и нечётким совпадением периода
- Кэш-логику (cache hit skip generation)
- Промпт-builder: формат user message
- Структуру seeded данных (3 записи, полные поля)
- Cron module (import ok, lifecycle start/stop)
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) in sys.path:
    sys.path.remove(str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

for _k in list(sys.modules):
    if _k == "web_cabinet" or _k.startswith("web_cabinet."):
        del sys.modules[_k]

import json
from unittest.mock import MagicMock, patch

import pytest

from web_cabinet.ai.models import (
    Anomaly,
    BriefSection,
    DateRange,
    KeyRecommendation,
    WeeklyBrief,
    WeeklyBriefRequest,
)
from web_cabinet.ai.prompts.weekly_brief import (
    WEEKLY_BRIEF_SYSTEM,
    build_weekly_brief_message,
)

SEEDED_PATH = (
    Path(__file__).parents[1]
    / "data" / "demo" / "investor_v1" / "weekly_briefs_seeded.json"
)

SAMPLE_LLM_JSON = {
    "title": "Недельный отчёт: 14–21 апреля 2026",
    "executive_summary": (
        "Неделя прошла с умеренным снижением надоя 28,4 кг/день (-2,4%). "
        "Главный успех — PR=24%, рекорд фермы. "
        "Требует внимания: рецидивный мастит у коровы №3142."
    ),
    "sections": [
        {
            "heading": "Продуктивность",
            "narrative": "Надой снизился на 0,7 кг из-за роста SCC.",
            "highlights": ["Надой 28,4 кг/день", "SCC 312 тыс/мл"],
            "evidence_ids": ["evt_milk_001"],
        },
        {
            "heading": "Воспроизводство",
            "narrative": "PR 24% — рекорд. 5 подтверждений из 6.",
            "highlights": ["PR 24% рекорд"],
            "evidence_ids": ["evt_repro_001"],
        },
        {
            "heading": "Здоровье",
            "narrative": "Рецидивный мастит у №3142. Индекс 94%.",
            "highlights": ["Мастит №3142 — рецидив"],
            "evidence_ids": ["evt_health_3142_002"],
        },
    ],
    "key_recommendations": [
        {
            "recommendation": "Изолировать молоко №3142",
            "priority": "high",
            "rationale": "Рецидив [evt_health_3142_002]",
            "expected_outcome": "SCC стада <280 тыс/мл",
            "affected_entities": ["cow_3142"],
        },
        {
            "recommendation": "CMT-тест группы A",
            "priority": "medium",
            "rationale": "SCC группы A вырос [evt_scc_herd_0421_001]",
            "expected_outcome": "Раннее выявление субклинического мастита",
            "affected_entities": ["group_a"],
        },
        {
            "recommendation": "Heat detection 25 апреля",
            "priority": "medium",
            "rationale": "PR 24% [evt_repro_001]",
            "expected_outcome": "8-10 осеменений",
            "affected_entities": ["group_a", "group_b"],
        },
    ],
    "anomalies_detected": [
        {
            "description": "SCC №3142 превысил 1 200 тыс/мл",
            "severity": "critical",
            "evidence_id": "evt_scc_3142_002",
        }
    ],
    "kpi_table": {
        "avg_milk_yield_kg": {"value": 28.4, "prev_period": 29.1, "delta_pct": -2.4, "unit": "кг/день"},
        "pregnancy_rate_pct": {"value": 24, "prev_period": 21, "delta_pct": 14.3, "unit": "%"},
    },
}


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestWeeklyBriefModel:
    def test_valid_model_minimal(self):
        brief = WeeklyBrief(
            farm_id="demo-farm-v1",
            period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="Тест",
            executive_summary="Краткое резюме.",
            generation_model="test",
        )
        assert brief.farm_id == "demo-farm-v1"
        assert brief.period.start == "2026-04-14"
        assert brief.brief_id.startswith("wb_")
        assert brief.sections == []
        assert brief.key_recommendations == []

    def test_valid_model_full(self):
        brief = WeeklyBrief(
            farm_id="demo-farm-v1",
            period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="Полный тест",
            executive_summary="Резюме с деталями.",
            sections=[BriefSection(heading="Продуктивность", narrative="Надой 28 кг.")],
            key_recommendations=[
                KeyRecommendation(
                    recommendation="Действие 1",
                    priority="high",
                    rationale="Причина",
                    expected_outcome="Результат",
                )
            ],
            anomalies_detected=[Anomaly(description="Аномалия", severity="warning", evidence_id="e1")],
            kpi_table={"avg_milk_yield_kg": {"value": 28.4, "prev_period": 29.1, "delta_pct": -2.4, "unit": "кг/день"}},
            generation_model="claude-opus-4-7",
            generation_tokens={"input": 1500, "output": 800},
        )
        assert len(brief.sections) == 1
        assert brief.sections[0].heading == "Продуктивность"
        assert brief.key_recommendations[0].priority == "high"
        assert brief.anomalies_detected[0].severity == "warning"

    def test_priority_literals(self):
        for p in ("high", "medium", "low"):
            rec = KeyRecommendation(
                recommendation="Действие",
                priority=p,  # type: ignore[arg-type]
                rationale="R",
                expected_outcome="O",
            )
            assert rec.priority == p

    def test_severity_literals(self):
        for s in ("critical", "warning", "info"):
            a = Anomaly(description="Аномалия", severity=s, evidence_id="e1")  # type: ignore[arg-type]
            assert a.severity == s

    def test_date_range_model(self):
        dr = DateRange(start="2026-04-14", end="2026-04-21")
        assert dr.start == "2026-04-14"
        assert dr.end == "2026-04-21"

    def test_brief_id_auto_generated(self):
        b1 = WeeklyBrief(
            farm_id="f1", period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="T", executive_summary="S", generation_model="m",
        )
        b2 = WeeklyBrief(
            farm_id="f1", period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="T", executive_summary="S", generation_model="m",
        )
        assert b1.brief_id != b2.brief_id


class TestWeeklyBriefRequest:
    def test_defaults(self):
        req = WeeklyBriefRequest()
        assert req.farm_id == "demo-farm-v1"
        assert req.start_date == ""
        assert req.end_date == ""
        assert req.language == "ru"
        assert req.deliver_email is False
        assert req.force_regenerate is False

    def test_custom_values(self):
        req = WeeklyBriefRequest(
            farm_id="my-farm",
            start_date="2026-04-14",
            end_date="2026-04-21",
            language="en",
            deliver_email=True,
        )
        assert req.farm_id == "my-farm"
        assert req.start_date == "2026-04-14"
        assert req.deliver_email is True


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_system_prompt_contains_key_rules(self):
        assert "ЗАПРЕЩЕНО" in WEEKLY_BRIEF_SYSTEM
        assert "executive_summary" in WEEKLY_BRIEF_SYSTEM
        assert "key_recommendations" in WEEKLY_BRIEF_SYSTEM
        assert "anomalies_detected" in WEEKLY_BRIEF_SYSTEM
        assert "kpi_table" in WEEKLY_BRIEF_SYSTEM
        assert "evidence" in WEEKLY_BRIEF_SYSTEM.lower()

    def test_system_prompt_sections_requirement(self):
        assert "Продуктивность" in WEEKLY_BRIEF_SYSTEM
        assert "Воспроизводство" in WEEKLY_BRIEF_SYSTEM
        assert "Здоровье" in WEEKLY_BRIEF_SYSTEM

    def test_message_builder_includes_period(self):
        msg = build_weekly_brief_message({"farm": "test"}, "2026-04-14", "2026-04-21")
        assert "2026-04-14" in msg
        assert "2026-04-21" in msg

    def test_message_builder_wraps_context(self):
        msg = build_weekly_brief_message({"farm": "test"}, "2026-04-14", "2026-04-21")
        assert "<farm_context>" in msg
        assert "</farm_context>" in msg

    def test_message_builder_with_to_text(self):
        class FakeCtx:
            def to_text(self) -> str:
                return "farm_text_content"
        msg = build_weekly_brief_message(FakeCtx(), "2026-04-14", "2026-04-21")
        assert "farm_text_content" in msg


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def _parse(
        self,
        data: dict,
        farm_id: str = "demo-farm-v1",
        start_date: str = "2026-04-14",
        end_date: str = "2026-04-21",
        model: str = "claude-opus-4-7",
    ) -> WeeklyBrief:
        from web_cabinet.ai.endpoints.weekly_brief import _parse_response
        content = json.dumps(data, ensure_ascii=False)
        return _parse_response(content, farm_id, start_date, end_date, model, 1500, 800)

    def test_parse_valid_full_response(self):
        result = self._parse(SAMPLE_LLM_JSON)
        assert result.farm_id == "demo-farm-v1"
        assert result.period.start == "2026-04-14"
        assert result.period.end == "2026-04-21"
        assert result.title == "Недельный отчёт: 14–21 апреля 2026"
        assert "28,4" in result.executive_summary
        assert len(result.sections) == 3
        assert len(result.key_recommendations) == 3
        assert len(result.anomalies_detected) == 1
        assert result.kpi_table["avg_milk_yield_kg"]["value"] == 28.4
        assert result.generation_model == "claude-opus-4-7"
        assert result.generation_tokens["input"] == 1500

    def test_parse_strips_markdown_fence(self):
        from web_cabinet.ai.endpoints.weekly_brief import _parse_response
        content = "```json\n" + json.dumps(SAMPLE_LLM_JSON) + "\n```"
        result = _parse_response(content, "demo-farm-v1", "2026-04-14", "2026-04-21", "m", 0, 0)
        assert result.executive_summary

    def test_parse_invalid_json_raises(self):
        from web_cabinet.ai.endpoints.weekly_brief import _parse_response
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_response("not json", "f", "2026-04-14", "2026-04-21", "m", 0, 0)

    def test_parse_minimal_response(self):
        from web_cabinet.ai.endpoints.weekly_brief import _parse_response
        minimal = {"executive_summary": "Минимальное резюме."}
        result = _parse_response(
            json.dumps(minimal), "demo-farm-v1", "2026-04-14", "2026-04-21", "m", 0, 0
        )
        assert result.executive_summary == "Минимальное резюме."
        assert result.sections == []
        assert result.key_recommendations == []

    def test_parse_sections_structure(self):
        result = self._parse(SAMPLE_LLM_JSON)
        headings = [s.heading for s in result.sections]
        assert "Продуктивность" in headings
        assert "Воспроизводство" in headings
        assert "Здоровье" in headings

    def test_parse_recommendation_priorities(self):
        result = self._parse(SAMPLE_LLM_JSON)
        priorities = {r.priority for r in result.key_recommendations}
        assert "high" in priorities
        assert "medium" in priorities

    def test_parse_anomaly_severity(self):
        result = self._parse(SAMPLE_LLM_JSON)
        assert result.anomalies_detected[0].severity == "critical"
        assert result.anomalies_detected[0].evidence_id == "evt_scc_3142_002"


# ---------------------------------------------------------------------------
# Seeded data tests
# ---------------------------------------------------------------------------

class TestSeededData:
    def test_seeded_file_exists(self):
        assert SEEDED_PATH.exists(), f"Seeded file not found: {SEEDED_PATH}"

    def test_seeded_file_valid_json(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        assert isinstance(records, list)
        assert len(records) >= 3, "Must have at least 3 seeded briefs"

    def test_seeded_records_have_required_fields(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        required = {"brief_id", "farm_id", "period", "title", "executive_summary",
                    "sections", "key_recommendations", "anomalies_detected", "kpi_table"}
        for rec in records:
            missing = required - set(rec.keys())
            assert not missing, f"brief_id={rec.get('brief_id')} missing: {missing}"

    def test_seeded_records_have_min_sections(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            assert len(rec.get("sections", [])) >= 3, (
                f"brief_id={rec['brief_id']}: need >=3 sections, got {len(rec.get('sections', []))}"
            )

    def test_seeded_records_have_min_recommendations(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            assert len(rec.get("key_recommendations", [])) >= 3, (
                f"brief_id={rec['brief_id']}: need >=3 recommendations"
            )

    def test_seeded_records_parse_to_model(self):
        from web_cabinet.ai.endpoints.weekly_brief import _brief_from_seeded
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            brief = _brief_from_seeded(rec, "demo-farm-v1")
            assert brief.farm_id == "demo-farm-v1"
            assert brief.generation_model == "demo-seeded"
            assert len(brief.executive_summary) > 30

    def test_seeded_period_fields(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            period = rec.get("period", {})
            assert "start" in period and "end" in period

    def test_seeded_kpi_table_structure(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            kpi = rec.get("kpi_table", {})
            assert len(kpi) >= 4, f"brief_id={rec['brief_id']}: too few KPIs"
            for k, v in kpi.items():
                if v is not None and isinstance(v, dict):
                    assert "value" in v, f"{k} missing 'value'"
                    assert "unit" in v, f"{k} missing 'unit'"

    def test_seeded_exact_period_match(self):
        from web_cabinet.ai.endpoints.weekly_brief import _load_seeded_brief
        brief = _load_seeded_brief("demo-farm-v1", "2026-04-14", "2026-04-21")
        assert brief.brief_id == "WBRIEF_20260421"
        assert brief.period.start == "2026-04-14"

    def test_seeded_fallback_when_no_match(self):
        from web_cabinet.ai.endpoints.weekly_brief import _load_seeded_brief
        brief = _load_seeded_brief("demo-farm-v1", "2099-01-01", "2099-01-07")
        assert brief.brief_id.startswith("WBRIEF_") or brief.brief_id.startswith("wb_")
        assert brief.generation_model in ("demo-seeded", "demo-fallback")

    def test_seeded_load_has_anomalies_first_record(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        first = records[0]
        assert len(first.get("anomalies_detected", [])) >= 1


# ---------------------------------------------------------------------------
# Cache logic
# ---------------------------------------------------------------------------

class TestCacheLogic:
    def test_cache_hit_skips_generation(self):
        cached_brief = WeeklyBrief(
            brief_id="wb_cached_001",
            farm_id="demo-farm-v1",
            period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="Кэшированный брифинг",
            executive_summary="Из кэша.",
            generation_model="demo-cached",
        )
        cached_json = cached_brief.model_dump_json()

        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = cached_json

        with patch("web_cabinet.ai.endpoints.weekly_brief.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.weekly_brief._load_seeded_brief") as mock_seeded:
                import asyncio
                from web_cabinet.ai.endpoints.weekly_brief import _generate_brief

                with patch("web_cabinet.ai.endpoints.weekly_brief.get_ai_settings") as mock_settings:
                    mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True
                    result = asyncio.run(_generate_brief("demo-farm-v1", "2026-04-14", "2026-04-21"))

                mock_seeded.assert_not_called()
                assert result.brief_id == "wb_cached_001"
                assert result.executive_summary == "Из кэша."

    def test_force_regenerate_skips_cache(self):
        cached_brief = WeeklyBrief(
            brief_id="wb_old",
            farm_id="demo-farm-v1",
            period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="Старый",
            executive_summary="Старый брифинг.",
            generation_model="demo-cached",
        )

        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = cached_brief.model_dump_json()

        new_brief = WeeklyBrief(
            brief_id="wb_new",
            farm_id="demo-farm-v1",
            period=DateRange(start="2026-04-14", end="2026-04-21"),
            title="Новый",
            executive_summary="Новый брифинг.",
            generation_model="demo-seeded",
        )

        with patch("web_cabinet.ai.endpoints.weekly_brief.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.weekly_brief._load_seeded_brief", return_value=new_brief):
                with patch("web_cabinet.ai.endpoints.weekly_brief.get_ai_settings") as mock_settings:
                    mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True
                    import asyncio
                    from web_cabinet.ai.endpoints.weekly_brief import _generate_brief
                    result = asyncio.run(
                        _generate_brief("demo-farm-v1", "2026-04-14", "2026-04-21", force_regenerate=True)
                    )
                    assert result.brief_id == "wb_new"


# ---------------------------------------------------------------------------
# Demo mode end-to-end
# ---------------------------------------------------------------------------

class TestDemoMode:
    def test_demo_mode_returns_seeded(self):
        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = None

        with patch("web_cabinet.ai.endpoints.weekly_brief.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.weekly_brief.get_ai_settings") as mock_settings:
                mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True
                import asyncio
                from web_cabinet.ai.endpoints.weekly_brief import _generate_brief
                result = asyncio.run(_generate_brief("demo-farm-v1", "2026-04-14", "2026-04-21"))
                assert result.farm_id == "demo-farm-v1"
                assert result.generation_model == "demo-seeded"
                assert len(result.sections) >= 3
                assert len(result.key_recommendations) >= 3

    def test_demo_mode_sets_cache(self):
        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = None

        with patch("web_cabinet.ai.endpoints.weekly_brief.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.weekly_brief.get_ai_settings") as mock_settings:
                mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True
                import asyncio
                from web_cabinet.ai.endpoints.weekly_brief import _generate_brief
                asyncio.run(_generate_brief("demo-farm-v1", "2026-04-14", "2026-04-21"))
                mock_cache.set.assert_called_once()


# ---------------------------------------------------------------------------
# Cron module
# ---------------------------------------------------------------------------

class TestCronModule:
    def test_cron_imports_ok(self):
        from web_cabinet.ai.background.weekly_brief_cron import (
            get_active_farms,
            start_cron,
            stop_cron,
        )
        assert callable(start_cron)
        assert callable(stop_cron)
        assert callable(get_active_farms)

    def test_get_active_farms_returns_list(self):
        from web_cabinet.ai.background.weekly_brief_cron import get_active_farms
        with patch("web_cabinet.ai.config.get_ai_settings") as mock_settings:
            mock_settings.return_value.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"
            farms = get_active_farms()
            assert isinstance(farms, list)
            assert len(farms) >= 1

    def test_stop_cron_when_not_started_is_safe(self):
        from web_cabinet.ai.background import weekly_brief_cron
        weekly_brief_cron._scheduler = None
        from web_cabinet.ai.background.weekly_brief_cron import stop_cron
        stop_cron()  # Must not raise


# ---------------------------------------------------------------------------
# Acceptance criteria validation
# ---------------------------------------------------------------------------

class TestAcceptanceCriteria:
    """Проверяем acceptance criteria MVP-N17 на seeded данных."""

    @pytest.fixture
    def seeded_brief(self):
        from web_cabinet.ai.endpoints.weekly_brief import _load_seeded_brief
        return _load_seeded_brief("demo-farm-v1", "2026-04-14", "2026-04-21")

    def test_ac1_returns_valid_weekly_brief(self, seeded_brief):
        # Use attribute check instead of isinstance to avoid cross-test module reload issues
        assert type(seeded_brief).__name__ == "WeeklyBrief"
        assert seeded_brief.farm_id
        assert seeded_brief.executive_summary

    def test_ac2_narrative_in_russian(self, seeded_brief):
        text = seeded_brief.executive_summary + " ".join(
            s.narrative for s in seeded_brief.sections
        )
        russian_chars = sum(1 for c in text if 'Ѐ' <= c <= 'ӿ')
        assert russian_chars > 50, "Narrative must be in Russian"

    def test_ac3_min_3_sections(self, seeded_brief):
        assert len(seeded_brief.sections) >= 3, "Must have at least 3 sections"

    def test_ac4_recommendations_with_rationale(self, seeded_brief):
        assert len(seeded_brief.key_recommendations) >= 3
        for rec in seeded_brief.key_recommendations:
            assert rec.rationale, f"Recommendation '{rec.recommendation}' missing rationale"
            assert rec.expected_outcome, f"Recommendation '{rec.recommendation}' missing expected_outcome"
            assert rec.priority in ("high", "medium", "low")

    def test_ac6_demo_mode_instant(self):
        import time
        from web_cabinet.ai.endpoints.weekly_brief import _load_seeded_brief
        t0 = time.monotonic()
        brief = _load_seeded_brief("demo-farm-v1", "2026-04-14", "2026-04-21")
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"Demo mode must be instant, took {elapsed:.2f}s"
        assert brief.generation_model == "demo-seeded"
