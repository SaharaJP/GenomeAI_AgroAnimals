"""Тесты для MVP-N16 Impact Narrative Generator.

Покрывает:
- Pydantic-валидацию ImpactNarrative и ImpactNarrativeRequest
- Парсинг JSON-ответа LLM в ImpactNarrative (_parse_response)
- Demo-режим: загрузку seeded narratives по event_id
- Кэш-логику (cache hit skip LLM call)
- Промпт-builder: формат user message
- Классификацию interpretation и significance
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure worktree root is first on sys.path so web_cabinet.ai is found here
# rather than from a stale cache or a different repo location.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) in sys.path:
    sys.path.remove(str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

# Evict any stale web_cabinet module so it's re-imported from the worktree
for _k in list(sys.modules):
    if _k == "web_cabinet" or _k.startswith("web_cabinet."):
        del sys.modules[_k]

import json
import re
from unittest.mock import MagicMock, patch

import pytest

from web_cabinet.ai.models import ImpactNarrative, ImpactNarrativeRequest
from web_cabinet.ai.prompts.impact_narrative import (
    IMPACT_NARRATIVE_SYSTEM,
    build_impact_narrative_message,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEEDED_PATH = (
    Path(__file__).parents[1]
    / "data" / "demo" / "investor_v1" / "seeded_impact_narratives.json"
)

SAMPLE_LLM_JSON = {
    "narrative": (
        "Мастит у Звёздочки 10 марта снизил удой с 36 до 28 кг/сутки (−22%) "
        "за 28 дней, потери составили 224 кг / 7 168 руб. "
        "Это значимый ущерб для 3-й лактации — граница категории «серьёзный». "
        "Рекомендуется повторный SCC-тест через 14 дней и оценка NPV при рецидиве."
    ),
    "interpretation": "negative",
    "significance": "major",
    "recommendations": [
        "Повторный SCC-тест через 14 дней после завершения Цефквина.",
        "NPV-расчёт при рецидиве.",
    ],
    "confidence": 0.88,
}


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestImpactNarrativeModel:
    def test_valid_model(self):
        n = ImpactNarrative(
            event_id="TL_001",
            window="4w",
            narrative="Тест narrative.",
            interpretation="negative",
            significance="major",
            recommendations=["Действие 1."],
            confidence=0.88,
            generation_model="claude-sonnet-4-6",
        )
        assert n.event_id == "TL_001"
        assert n.interpretation == "negative"
        assert n.significance == "major"
        assert 0.0 <= n.confidence <= 1.0

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ImpactNarrative(
                event_id="X",
                window="1w",
                narrative="N",
                interpretation="neutral",
                significance="minor",
                recommendations=[],
                confidence=1.5,
                generation_model="test",
            )
        with pytest.raises(Exception):
            ImpactNarrative(
                event_id="X",
                window="1w",
                narrative="N",
                interpretation="neutral",
                significance="minor",
                recommendations=[],
                confidence=-0.1,
                generation_model="test",
            )

    def test_interpretation_literals(self):
        for val in ("positive", "negative", "neutral", "mixed"):
            n = ImpactNarrative(
                event_id="ev", window="1w", narrative="n",
                interpretation=val,  # type: ignore[arg-type]
                significance="minor", recommendations=[], confidence=0.5,
                generation_model="test",
            )
            assert n.interpretation == val

    def test_significance_literals(self):
        for val in ("major", "moderate", "minor", "insignificant"):
            n = ImpactNarrative(
                event_id="ev", window="1w", narrative="n",
                interpretation="neutral",
                significance=val,  # type: ignore[arg-type]
                recommendations=[], confidence=0.5, generation_model="test",
            )
            assert n.significance == val

    def test_generated_at_auto_filled(self):
        n = ImpactNarrative(
            event_id="ev", window="1w", narrative="n", interpretation="neutral",
            significance="minor", recommendations=[], confidence=0.5, generation_model="test",
        )
        assert n.generated_at  # not empty


class TestImpactNarrativeRequest:
    def test_defaults(self):
        req = ImpactNarrativeRequest(event_id="TL_001")
        assert req.window == "1w"
        assert req.language == "ru"
        assert req.farm_id == "demo-farm-v1"

    def test_window_literals(self):
        for w in ("3d", "1w", "2w", "4w"):
            req = ImpactNarrativeRequest(event_id="e", window=w)  # type: ignore[arg-type]
            assert req.window == w

    def test_invalid_window(self):
        with pytest.raises(Exception):
            ImpactNarrativeRequest(event_id="e", window="5w")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_system_prompt_contains_key_rules(self):
        assert "ЗАПРЕЩЕНО" in IMPACT_NARRATIVE_SYSTEM
        assert "confidence" in IMPACT_NARRATIVE_SYSTEM
        assert "2-3 предложения" in IMPACT_NARRATIVE_SYSTEM or "ровно 2-3" in IMPACT_NARRATIVE_SYSTEM
        assert "JSON" in IMPACT_NARRATIVE_SYSTEM

    def test_message_builder_includes_all_sections(self):
        event = {"timeline_event_id": "TL_001", "event_type": "mastitis"}
        before = {"milk_yield": {"value": 36.0, "period": "до события (28д)"}}
        after = {"milk_yield": {"value": 28.0, "period": "после события (28д)"}}
        related = [{"timeline_event_id": "TL_002", "event_type": "pen_move"}]

        msg = build_impact_narrative_message(event, before, after, related)

        assert "TL_001" in msg
        assert "milk_yield" in msg
        assert "36" in msg
        assert "28" in msg
        assert "TL_002" in msg
        assert "before_metrics" in msg
        assert "after_metrics" in msg
        assert "related_events" in msg

    def test_message_builder_valid_json_payload(self):
        event = {"id": "e1"}
        before = {"x": {"value": 10}}
        after = {"x": {"value": 8}}
        related: list = []

        msg = build_impact_narrative_message(event, before, after, related)
        # Extract the JSON block from the message
        start = msg.index("{")
        end = msg.rindex("}") + 1
        payload = json.loads(msg[start:end])
        assert "event" in payload
        assert "before_metrics" in payload
        assert "after_metrics" in payload


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def _parse(self, data: dict, event_id: str = "TL_001", window: str = "4w", model: str = "claude-sonnet-4-6"):
        from web_cabinet.ai.endpoints.impact_narrative import _parse_response
        content = json.dumps(data, ensure_ascii=False)
        return _parse_response(content, event_id, window, model)

    def test_parse_valid_response(self):
        result = self._parse(SAMPLE_LLM_JSON)
        assert result.event_id == "TL_001"
        assert result.window == "4w"
        assert result.interpretation == "negative"
        assert result.significance == "major"
        assert len(result.recommendations) == 2
        assert result.confidence == pytest.approx(0.88)
        assert result.generation_model == "claude-sonnet-4-6"
        assert "Мастит" in result.narrative

    def test_parse_strips_markdown_fence(self):
        from web_cabinet.ai.endpoints.impact_narrative import _parse_response
        content = "```json\n" + json.dumps(SAMPLE_LLM_JSON) + "\n```"
        result = _parse_response(content, "TL_001", "1w", "test")
        assert result.narrative

    def test_parse_invalid_json_raises(self):
        from web_cabinet.ai.endpoints.impact_narrative import _parse_response
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_response("not json at all", "e", "1w", "m")

    def test_parse_defaults_on_missing_fields(self):
        from web_cabinet.ai.endpoints.impact_narrative import _parse_response
        minimal = {"narrative": "Тест."}
        result = _parse_response(json.dumps(minimal), "e", "1w", "m")
        assert result.narrative == "Тест."
        assert result.interpretation == "neutral"
        assert result.significance == "minor"
        assert result.recommendations == []
        assert result.confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Demo mode — seeded narratives
# ---------------------------------------------------------------------------

class TestSeededNarratives:
    def test_seeded_file_exists(self):
        assert SEEDED_PATH.exists(), f"Seeded file not found: {SEEDED_PATH}"

    def test_seeded_file_valid_json(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        assert isinstance(records, list)
        assert len(records) >= 8

    def test_seeded_records_have_required_fields(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        required = {"event_id", "window", "narrative", "interpretation", "significance",
                    "recommendations", "confidence", "generation_model"}
        for rec in records:
            missing = required - set(rec.keys())
            assert not missing, f"event_id={rec.get('event_id')} missing: {missing}"

    def test_seeded_narratives_parse_to_model(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            rec_copy = dict(rec)
            rec_copy.setdefault("generated_at", "2026-04-23T00:00:00")
            n = ImpactNarrative(**rec_copy)
            assert len(n.narrative) > 20, f"narrative too short for {rec['event_id']}"
            assert 0.0 <= n.confidence <= 1.0

    def test_seeded_load_by_event_id(self):
        from web_cabinet.ai.endpoints.impact_narrative import _load_seeded_narrative
        n = _load_seeded_narrative("TL_001", "4w")
        assert n.event_id == "TL_001"
        assert n.interpretation == "negative"
        assert n.significance == "major"
        assert n.generation_model == "demo-seeded"

    def test_seeded_unknown_event_returns_fallback(self):
        from web_cabinet.ai.endpoints.impact_narrative import _load_seeded_narrative
        n = _load_seeded_narrative("TL_UNKNOWN_999", "1w")
        assert n.event_id == "TL_UNKNOWN_999"
        assert n.interpretation == "neutral"
        assert n.generation_model == "demo-fallback"

    def test_seeded_narratives_2_to_3_sentences(self):
        """Narrative должен быть 2-3 предложения.

        Разбиваем по точке/!/? только когда за ней идёт пробел+заглавная или конец строки,
        чтобы не разрезать десятичные числа (11.2, 33.6 и т.п.).
        """
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        for rec in records:
            narrative = rec["narrative"].strip()
            # Split on sentence-ending punctuation followed by space+capital or end of string
            sentences = re.split(r"[.!?](?=\s+[А-ЯA-Z]|$)", narrative)
            sentences = [s.strip() for s in sentences if s.strip()]
            assert 2 <= len(sentences) <= 3, (
                f"event_id={rec['event_id']}: expected 2-3 sentences, "
                f"got {len(sentences)}: {narrative}"
            )

    def test_seeded_covers_all_8_demo_events(self):
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        event_ids = {r["event_id"] for r in records}
        expected = {"TL_001", "TL_002", "TL_003", "TL_004", "TL_005", "TL_006", "TL_007", "TL_008"}
        assert expected <= event_ids, f"Missing events: {expected - event_ids}"


# ---------------------------------------------------------------------------
# Cache logic
# ---------------------------------------------------------------------------

class TestCacheLogic:
    def test_cache_hit_skips_seeded_load(self):
        """При cache hit endpoint не вызывает _load_seeded_narrative."""
        cached_narrative = ImpactNarrative(
            event_id="TL_001", window="1w",
            narrative="Cached narrative.",
            interpretation="positive", significance="minor",
            recommendations=[], confidence=0.9,
            generation_model="demo-cached",
        )
        cached_json = cached_narrative.model_dump_json()

        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = cached_json

        with patch("web_cabinet.ai.endpoints.impact_narrative.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.impact_narrative._load_seeded_narrative") as mock_seeded:
                import asyncio
                from web_cabinet.ai.endpoints.impact_narrative import generate_impact_narrative

                req = ImpactNarrativeRequest(event_id="TL_001", window="1w")

                with patch("web_cabinet.ai.config.get_ai_settings") as mock_settings:
                    mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True
                    result = asyncio.run(generate_impact_narrative(req))

                mock_seeded.assert_not_called()
                assert result.narrative == "Cached narrative."

    def test_cache_miss_calls_seeded_and_sets_cache(self):
        """При cache miss в demo-режиме вызывает seeded и записывает в кэш."""
        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get.return_value = None

        expected = ImpactNarrative(
            event_id="TL_001", window="1w",
            narrative="Seeded narrative.", interpretation="negative",
            significance="major", recommendations=["Rec1"], confidence=0.88,
            generation_model="demo-seeded",
        )

        with patch("web_cabinet.ai.endpoints.impact_narrative.get_cache", return_value=mock_cache):
            with patch("web_cabinet.ai.endpoints.impact_narrative._load_seeded_narrative",
                       return_value=expected) as mock_seeded:
                with patch("web_cabinet.ai.endpoints.impact_narrative.get_ai_settings") as mock_settings:
                    mock_settings.return_value.GENOMEAI_AI_DEMO_MODE = True

                    import asyncio
                    from web_cabinet.ai.endpoints.impact_narrative import generate_impact_narrative

                    req = ImpactNarrativeRequest(event_id="TL_001")
                    result = asyncio.run(generate_impact_narrative(req))

                    mock_seeded.assert_called_once_with("TL_001", "1w")
                    mock_cache.set.assert_called_once()
                    assert result.narrative == "Seeded narrative."


# ---------------------------------------------------------------------------
# Classification validation on typical cases
# ---------------------------------------------------------------------------

class TestClassification:
    """Проверяем, что seeded данные корректно классифицированы для типовых кейсов."""

    @pytest.fixture
    def seeded(self) -> dict[str, dict]:
        records = json.loads(SEEDED_PATH.read_text(encoding="utf-8"))
        return {r["event_id"]: r for r in records}

    def test_mastitis_is_negative_major(self, seeded):
        assert seeded["TL_001"]["interpretation"] == "negative"
        assert seeded["TL_001"]["significance"] == "major"

    def test_culling_trigger_is_negative_major(self, seeded):
        assert seeded["TL_004"]["interpretation"] == "negative"
        assert seeded["TL_004"]["significance"] == "major"

    def test_heat_detection_wave_is_positive(self, seeded):
        assert seeded["TL_007"]["interpretation"] == "positive"

    def test_calving_wave_is_positive(self, seeded):
        assert seeded["TL_008"]["interpretation"] == "positive"

    def test_all_have_at_least_one_recommendation(self, seeded):
        for event_id, rec in seeded.items():
            assert len(rec["recommendations"]) >= 1, (
                f"{event_id} has no recommendations"
            )

    def test_major_events_have_high_confidence(self, seeded):
        major_events = [eid for eid, r in seeded.items() if r["significance"] == "major"]
        for eid in major_events:
            assert seeded[eid]["confidence"] >= 0.85, (
                f"{eid} is major but confidence={seeded[eid]['confidence']}"
            )
