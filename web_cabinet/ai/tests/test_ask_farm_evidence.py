"""Тесты evidence validation pipeline для ask-farm endpoint (MVP-N13-b)."""
from __future__ import annotations

import pytest

from web_cabinet.ai.endpoints.ask_farm import (
    _extract_known_event_ids,
    parse_evidence_from_response,
)
from web_cabinet.ai.prompts.ask_farm import ASK_FARM_SYSTEM


# ---------------------------------------------------------------------------
# parse_evidence_from_response
# ---------------------------------------------------------------------------

class TestParseEvidenceFromResponse:
    def test_known_evidence_verified(self):
        answer = "SCC у коровы 4821 — 450 тыс. [evidence: event_4821_scc_spike]."
        result = parse_evidence_from_response(answer, {"event_4821_scc_spike"})
        assert len(result) == 1
        assert result[0].event_id == "event_4821_scc_spike"
        assert result[0].verified is True

    def test_unknown_evidence_unverified(self):
        answer = "Корова в норме [evidence: event_hallucinated_999]."
        result = parse_evidence_from_response(answer, set())
        assert len(result) == 1
        assert result[0].verified is False
        assert "⚠" in result[0].description
        assert "event_hallucinated_999" in result[0].description

    def test_mixed_verified_and_unverified(self):
        answer = (
            "SCC высокий [evidence: event_4821_scc_spike]. "
            "Также обнаружено [evidence: event_ghost_xyz]."
        )
        known = {"event_4821_scc_spike"}
        result = parse_evidence_from_response(answer, known)
        assert len(result) == 2
        by_id = {e.event_id: e for e in result}
        assert by_id["event_4821_scc_spike"].verified is True
        assert by_id["event_ghost_xyz"].verified is False

    def test_no_evidence_returns_empty(self):
        answer = "В текущих данных фермы информации об этой корове нет."
        result = parse_evidence_from_response(answer, {"event_4821_scc_spike"})
        assert result == []

    def test_duplicate_evidence_deduplicated(self):
        answer = (
            "Первое упоминание [evidence: event_001]. "
            "Второе упоминание того же события [evidence: event_001]."
        )
        result = parse_evidence_from_response(answer, {"event_001"})
        assert len(result) == 1
        assert result[0].event_id == "event_001"

    def test_evidence_with_dashes_in_id(self):
        answer = "Событие [evidence: event-heat-batch-20260421]."
        result = parse_evidence_from_response(answer, {"event-heat-batch-20260421"})
        assert result[0].verified is True


# ---------------------------------------------------------------------------
# _extract_known_event_ids
# ---------------------------------------------------------------------------

class TestExtractKnownEventIds:
    def test_extracts_from_recent_events(self):
        ctx = {
            "recent_events": [
                {"evidence_id": "event_4821_scc_spike", "type": "health"},
                {"evidence_id": "event_heat_batch_20260421", "type": "repro"},
            ]
        }
        ids = _extract_known_event_ids(ctx)
        assert "event_4821_scc_spike" in ids
        assert "event_heat_batch_20260421" in ids

    def test_ignores_empty_and_nan_ids(self):
        ctx = {
            "recent_events": [
                {"evidence_id": "", "type": "health"},
                {"evidence_id": "nan", "type": "other"},
                {"evidence_id": "  ", "type": "other"},
            ]
        }
        ids = _extract_known_event_ids(ctx)
        assert len(ids) == 0

    def test_extracts_from_full_profiles(self):
        ctx = {
            "recent_events": [],
            "full_profiles": {
                "4821": {
                    "health_events": [{"event_id": "he_4821_001"}],
                    "treatments": [{"treatment_id": "tr_4821_001"}],
                }
            },
        }
        ids = _extract_known_event_ids(ctx)
        assert "he_4821_001" in ids
        assert "tr_4821_001" in ids

    def test_unknown_cow_events_not_in_ids(self):
        """Events for cow X99999 (not in context) are absent → AI reference will be unverified."""
        ctx = {
            "recent_events": [
                {"evidence_id": "event_4821_scc_spike", "type": "health"},
            ]
        }
        ids = _extract_known_event_ids(ctx)
        # Если AI выдумает ссылку на несуществующую корову
        fake_ref = "event_X99999_scc_fake"
        assert fake_ref not in ids
        # Проверяем что pipeline поймает это
        evidences = parse_evidence_from_response(
            f"Корова X99999 в норме [evidence: {fake_ref}].",
            ids,
        )
        assert len(evidences) == 1
        assert evidences[0].verified is False


# ---------------------------------------------------------------------------
# System prompt requirements
# ---------------------------------------------------------------------------

class TestAskFarmSystemPrompt:
    def test_evidence_format_specified(self):
        assert "[evidence:" in ASK_FARM_SYSTEM

    def test_honest_about_missing_data(self):
        assert "ЕСЛИ ДАННЫХ НЕТ" in ASK_FARM_SYSTEM or "не найдено" in ASK_FARM_SYSTEM.lower()

    def test_unknown_animal_instruction(self):
        """Промпт должен явно инструктировать честно сообщать об отсутствующих животных."""
        lower = ASK_FARM_SYSTEM.lower()
        has_instruction = (
            "не найдено" in lower
            or "не найден" in lower
            or "не придумывай" in lower
        )
        assert has_instruction, "Промпт должен инструктировать честно сообщать об отсутствующих данных"

    def test_russian_language_enforced(self):
        lower = ASK_FARM_SYSTEM.lower()
        assert "русский" in lower or "русск" in lower or "только русский" in lower

    def test_no_hallucination_rule(self):
        lower = ASK_FARM_SYSTEM.lower()
        has_rule = "не придумывай" in lower or "запрещено" in lower or "только с данными" in lower
        assert has_rule
