"""Tests for MVP-N15 Insight Scanner.

Covers:
- ScannerInsight / ScannerRecommendation model validation
- _parse_insights: valid JSON, empty list, malformed JSON
- _validate_evidence: pass/fail
- _deduplicate: removes overlapping evidence_ids
- scan_for_new_insights demo mode: returns seeded data
- scan_for_new_insights live mode: mocked Claude call
- _coerce_category / _coerce_priority: mapping edge cases
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_wt_root = Path(__file__).resolve().parents[3]
if str(_wt_root) not in sys.path:
    sys.path.insert(0, str(_wt_root))
else:
    sys.path.remove(str(_wt_root))
    sys.path.insert(0, str(_wt_root))

# Evict any web_cabinet loaded from main-repo (which lacks ai/ subpackage)
for _key in list(sys.modules.keys()):
    if _key == "web_cabinet" or _key.startswith("web_cabinet."):
        del sys.modules[_key]

from datetime import datetime, timedelta

from web_cabinet.ai.models import ScannerInsight, ScannerRecommendation
from web_cabinet.ai.background.insight_scanner import (
    _coerce_category,
    _coerce_priority,
    _deduplicate,
    _insight_from_dict,
    _parse_insights,
    _validate_evidence,
    scan_for_new_insights,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_REC = {
    "insight_id": "ins_test0001",
    "title": "Тестовый инсайт",
    "description": "Описание с цифрами: SCC 450k, рост 7 дней",
    "category": "health",
    "priority": "high",
    "affected_cow_ids": ["9002"],
    "affected_group_ids": [],
    "evidence_ids": ["HE_9002_SCC"],
    "recommendations": [
        {
            "action": "Провести осмотр",
            "priority": "high",
            "role": "vet",
            "due_hint": "в течение 4 часов",
        }
    ],
}


# ---------------------------------------------------------------------------
# ScannerInsight model
# ---------------------------------------------------------------------------

class TestScannerInsightModel:
    def test_valid_construction(self):
        ins = ScannerInsight(
            farm_id="demo-farm-v1",
            title="Test",
            description="desc",
            category="health",
            priority="high",
        )
        assert ins.status == "to_check"
        assert ins.generator == "ai_scanner"
        assert ins.insight_id.startswith("ins_")

    def test_all_categories_valid(self):
        for cat in ("production", "reproduction", "health", "feeding", "welfare", "economics"):
            ins = ScannerInsight(farm_id="f", title="t", description="d", category=cat, priority="low")
            assert ins.category == cat

    def test_all_priorities_valid(self):
        for pri in ("high", "medium", "low"):
            ins = ScannerInsight(farm_id="f", title="t", description="d", category="health", priority=pri)
            assert ins.priority == pri

    def test_invalid_category_raises(self):
        with pytest.raises(Exception):
            ScannerInsight(farm_id="f", title="t", description="d", category="unknown", priority="low")

    def test_recommendation_model(self):
        rec = ScannerRecommendation(action="Do it", priority="high", role="vet")
        assert rec.due_hint is None


# ---------------------------------------------------------------------------
# _insight_from_dict
# ---------------------------------------------------------------------------

class TestInsightFromDict:
    def test_valid_dict(self):
        ins = _insight_from_dict(_VALID_REC, "demo-farm-v1")
        assert ins is not None
        assert ins.insight_id == "ins_test0001"
        assert ins.category == "health"
        assert ins.priority == "high"
        assert ins.evidence_ids == ["HE_9002_SCC"]
        assert len(ins.recommendations) == 1
        assert ins.recommendations[0].role == "vet"

    def test_missing_insight_id_gets_generated(self):
        rec = {**_VALID_REC, "insight_id": None}
        ins = _insight_from_dict(rec, "demo-farm-v1")
        assert ins is not None
        assert ins.insight_id.startswith("ins_")

    def test_seeded_format_animal_ids(self):
        rec = {**_VALID_REC, "animal_ids": ["3142"], "affected_cow_ids": []}
        ins = _insight_from_dict(rec, "demo-farm-v1")
        assert ins is not None
        assert "3142" in ins.affected_cow_ids

    def test_missing_required_field_returns_none(self):
        rec = {"insight_id": "x"}  # no title/description/category/priority
        ins = _insight_from_dict(rec, "demo-farm-v1")
        assert ins is None


# ---------------------------------------------------------------------------
# _parse_insights
# ---------------------------------------------------------------------------

class TestParseInsights:
    def test_valid_json_array(self):
        content = json.dumps([_VALID_REC])
        results = _parse_insights(content, "demo-farm-v1")
        assert len(results) == 1
        assert results[0].title == "Тестовый инсайт"

    def test_markdown_fenced_json(self):
        content = f"```json\n{json.dumps([_VALID_REC])}\n```"
        results = _parse_insights(content, "demo-farm-v1")
        assert len(results) == 1

    def test_empty_array(self):
        results = _parse_insights("[]", "demo-farm-v1")
        assert results == []

    def test_malformed_json_returns_empty(self):
        results = _parse_insights("not json at all", "demo-farm-v1")
        assert results == []

    def test_non_list_json_returns_empty(self):
        results = _parse_insights('{"key": "value"}', "demo-farm-v1")
        assert results == []

    def test_max_5_insights(self):
        many = [_VALID_REC] * 10
        results = _parse_insights(json.dumps(many), "demo-farm-v1")
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# _validate_evidence
# ---------------------------------------------------------------------------

class TestValidateEvidence:
    def test_valid_with_evidence(self):
        ins = _insight_from_dict(_VALID_REC, "demo-farm-v1")
        assert _validate_evidence(ins) is True

    def test_invalid_no_evidence(self):
        rec = {**_VALID_REC, "evidence_ids": []}
        ins = _insight_from_dict(rec, "demo-farm-v1")
        assert _validate_evidence(ins) is False


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_no_overlap(self):
        ins = _insight_from_dict(_VALID_REC, "demo-farm-v1")
        existing = [{"evidence_ids": ["OTHER_EVT"]}]
        result = _deduplicate([ins], existing)
        assert len(result) == 1

    def test_exact_overlap_removed(self):
        ins = _insight_from_dict(_VALID_REC, "demo-farm-v1")
        existing = [{"evidence_ids": ["HE_9002_SCC"]}]
        result = _deduplicate([ins], existing)
        assert len(result) == 0

    def test_empty_existing(self):
        ins = _insight_from_dict(_VALID_REC, "demo-farm-v1")
        result = _deduplicate([ins], [])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _coerce_category / _coerce_priority
# ---------------------------------------------------------------------------

class TestCoerceFunctions:
    @pytest.mark.parametrize("raw,expected", [
        ("health", "health"),
        ("health_alert", "health"),
        ("yield_drop_analysis", "production"),
        ("culling_recommendation", "economics"),
        ("pregnancy_rate", "reproduction"),
        ("unknown_type", "production"),
    ])
    def test_coerce_category(self, raw, expected):
        assert _coerce_category(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("high", "high"),
        ("urgent", "high"),
        ("critical", "high"),
        ("medium", "medium"),
        ("warn", "medium"),
        ("warning", "medium"),
        ("low", "low"),
        ("info", "low"),
    ])
    def test_coerce_priority(self, raw, expected):
        assert _coerce_priority(raw) == expected


# ---------------------------------------------------------------------------
# scan_for_new_insights — demo mode
# ---------------------------------------------------------------------------

_SETTINGS_MOD = "web_cabinet.ai.background.insight_scanner.get_ai_settings"


def _demo_settings() -> MagicMock:
    s = MagicMock()
    s.GENOMEAI_AI_DEMO_MODE = True
    s.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"
    return s


class TestScanForNewInsightsDemo:
    def test_demo_mode_returns_seeded_insights(self):
        with patch(_SETTINGS_MOD, return_value=_demo_settings()):
            results = scan_for_new_insights("demo-farm-v1")

        assert isinstance(results, list)
        assert len(results) > 0
        for ins in results:
            assert isinstance(ins, ScannerInsight)
            assert ins.farm_id == "demo-farm-v1"

    def test_demo_mode_all_have_titles(self):
        with patch(_SETTINGS_MOD, return_value=_demo_settings()):
            results = scan_for_new_insights("demo-farm-v1")

        for ins in results:
            assert ins.title, f"Insight {ins.insight_id} has empty title"

    def test_demo_mode_max_5_insights(self):
        with patch(_SETTINGS_MOD, return_value=_demo_settings()):
            results = scan_for_new_insights("demo-farm-v1")

        assert len(results) <= 5


# ---------------------------------------------------------------------------
# scan_for_new_insights — live mode (mocked Claude)
# ---------------------------------------------------------------------------

_SCANNER_MOD = "web_cabinet.ai.background.insight_scanner"


class TestScanForNewInsightsLive:
    def _make_settings(self, demo: bool = False) -> MagicMock:
        s = MagicMock()
        s.GENOMEAI_AI_DEMO_MODE = demo
        s.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"
        return s

    def _make_client(self, content: str) -> MagicMock:
        mock_llm = MagicMock()
        mock_llm.content = content

        async def fake_agenerate(*args, **kwargs):
            return mock_llm

        mock_client = MagicMock()
        mock_client.agenerate = fake_agenerate
        return mock_client

    def test_live_mode_parses_claude_response(self):
        content = json.dumps([
            {
                "insight_id": "ins_live001",
                "title": "Живой инсайт из Claude",
                "description": "SCC 420k, рост за 5 дней",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["9002"],
                "affected_group_ids": [],
                "evidence_ids": ["HE_9002_SCC"],
                "recommendations": [
                    {
                        "action": "Осмотр ветеринара",
                        "priority": "high",
                        "role": "vet",
                        "due_hint": "в течение 4 часов",
                    }
                ],
            }
        ])

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=self._make_settings(demo=False)),
            patch(f"{_SCANNER_MOD}.build_farm_context", return_value={}),
            patch(f"{_SCANNER_MOD}.get_active_insights", return_value=[]),
            patch(f"{_SCANNER_MOD}.get_client", return_value=self._make_client(content)),
            patch(f"{_SCANNER_MOD}.save_insight"),
        ):
            results = scan_for_new_insights("demo-farm-v1")

        assert len(results) == 1
        assert results[0].insight_id == "ins_live001"
        assert results[0].category == "health"
        assert results[0].priority == "high"
        assert results[0].evidence_ids == ["HE_9002_SCC"]

    def test_live_mode_filters_no_evidence(self):
        """Инсайты без evidence_ids должны отфильтровываться."""
        content = json.dumps([
            {
                "insight_id": "ins_noevidence",
                "title": "Без доказательств",
                "description": "Нет evidence",
                "category": "production",
                "priority": "low",
                "affected_cow_ids": [],
                "affected_group_ids": [],
                "evidence_ids": [],
                "recommendations": [],
            }
        ])

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=self._make_settings(demo=False)),
            patch(f"{_SCANNER_MOD}.build_farm_context", return_value={}),
            patch(f"{_SCANNER_MOD}.get_active_insights", return_value=[]),
            patch(f"{_SCANNER_MOD}.get_client", return_value=self._make_client(content)),
            patch(f"{_SCANNER_MOD}.save_insight"),
        ):
            results = scan_for_new_insights("demo-farm-v1")

        assert results == []


# ---------------------------------------------------------------------------
# New tests: bridge integration, sensor serialization, 7-day dedup
# ---------------------------------------------------------------------------

def _live_settings() -> MagicMock:
    s = MagicMock()
    s.GENOMEAI_AI_DEMO_MODE = False
    s.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"
    return s


class TestScannerDemoModeUsesSeeded:
    """Demo mode must return seeded JSON without calling bridges or Claude."""

    def test_scanner_demo_mode_uses_seeded(self):
        demo_s = MagicMock()
        demo_s.GENOMEAI_AI_DEMO_MODE = True
        demo_s.GENOMEAI_DEMO_FARM_ID = "demo-farm-v1"

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=demo_s),
            patch(f"{_SCANNER_MOD}.build_farm_context") as mock_ctx_builder,
            patch(f"{_SCANNER_MOD}.get_client") as mock_client_getter,
        ):
            results = scan_for_new_insights("demo-farm-v1")

        # No bridge or Claude calls in demo mode
        mock_ctx_builder.assert_not_called()
        mock_client_getter.assert_not_called()

        assert isinstance(results, list)
        assert len(results) > 0
        for ins in results:
            assert isinstance(ins, ScannerInsight)


class TestScannerRealModeFindsSeededAnomalies:
    """Real mode must include sensor_anomalies in context sent to Claude."""

    def _make_claude_client(self, content: str) -> MagicMock:
        captured: list[str] = []

        async def fake_agenerate(message, **kwargs):
            captured.append(message)
            resp = MagicMock()
            resp.content = content
            return resp

        mock_client = MagicMock()
        mock_client.agenerate = fake_agenerate
        mock_client._captured = captured
        return mock_client

    def test_scanner_real_mode_finds_seeded_anomalies(self):
        from datetime import date
        from web_cabinet.ai.context import FarmContext
        from web_cabinet.analytics.sensor_bridge import SensorAnomaly

        sensor_anomalies = [
            SensorAnomaly("4821", "demo-farm-v1", "scc_spike", date.today(), 450.0, 200.0, "Звёздочка SCC 450k"),
            SensorAnomaly("7001", "demo-farm-v1", "yield_drop", date.today(), 15.0, 20.0, "Малина yield drop 17%"),
            SensorAnomaly("9002", "demo-farm-v1", "scc_spike", date.today(), 280.0, 200.0, "Ночка SCC 280k"),
        ]
        mock_ctx = FarmContext(farm_id="demo-farm-v1", sensor_anomalies=sensor_anomalies)

        claude_payload = json.dumps([
            {
                "insight_id": "ins_z01xxxx",
                "title": "SCC spike Звёздочка",
                "description": "SCC 450k uptrend 9 days",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["4821"],
                "affected_group_ids": [],
                "evidence_ids": ["SENS_SCC_4821"],
                "recommendations": [{"action": "Vet check", "priority": "high", "role": "vet"}],
            },
            {
                "insight_id": "ins_m01xxxx",
                "title": "Yield drop Малина",
                "description": "Yield dropped 17%",
                "category": "production",
                "priority": "medium",
                "affected_cow_ids": ["7001"],
                "affected_group_ids": [],
                "evidence_ids": ["SENS_YIELD_7001"],
                "recommendations": [{"action": "Check feeding", "priority": "medium", "role": "zootech"}],
            },
            {
                "insight_id": "ins_n01xxxx",
                "title": "SCC spike Ночка",
                "description": "SCC 280k uptrend",
                "category": "health",
                "priority": "medium",
                "affected_cow_ids": ["9002"],
                "affected_group_ids": [],
                "evidence_ids": ["SENS_SCC_9002"],
                "recommendations": [{"action": "Monitor SCC", "priority": "medium", "role": "vet"}],
            },
        ])
        mock_client = self._make_claude_client(claude_payload)

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=_live_settings()),
            patch(f"{_SCANNER_MOD}.build_farm_context", return_value=mock_ctx),
            patch(f"{_SCANNER_MOD}.get_active_insights", return_value=[]),
            patch(f"{_SCANNER_MOD}.get_client", return_value=mock_client),
            patch(f"{_SCANNER_MOD}.save_insight"),
        ):
            results = scan_for_new_insights("demo-farm-v1")

        # At least 3 insights returned
        assert len(results) >= 3

        cow_ids = {cid for ins in results for cid in ins.affected_cow_ids}
        assert "4821" in cow_ids, "Звёздочка (4821) missing"
        assert "7001" in cow_ids, "Малина (7001) missing"
        assert "9002" in cow_ids, "Ночка (9002) missing"

        # Sensor anomalies must appear in the prompt sent to Claude
        assert len(mock_client._captured) == 1
        prompt_sent = mock_client._captured[0]
        assert "АНОМАЛИИ СЕНСОРОВ" in prompt_sent, (
            "sensor_anomalies section missing from prompt; "
            "_serialize_for_claude likely not called"
        )
        assert "4821" in prompt_sent
        assert "scc_spike" in prompt_sent


class TestScannerDedup7Days:
    """7-day same-animal+category dedup must prevent duplicate insights."""

    def _make_claude_client(self, content: str) -> MagicMock:
        async def fake_agenerate(message, **kwargs):
            resp = MagicMock()
            resp.content = content
            return resp

        mock_client = MagicMock()
        mock_client.agenerate = fake_agenerate
        return mock_client

    def test_scanner_dedup_skips_existing(self):
        """New insight for cow+category already seen in last 7 days is dropped."""
        existing = [
            {
                "insight_id": "ins_existing",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["4821"],
                "evidence_ids": ["SENS_SCC_4821_OLD"],
                "generated_at_utc": (datetime.utcnow() - timedelta(days=3)).isoformat(),
                "title": "Existing SCC insight",
            }
        ]

        # Claude returns a new insight for the SAME cow+category (different evidence)
        new_insight_content = json.dumps([
            {
                "insight_id": "ins_new001x",
                "title": "New SCC spike same cow",
                "description": "SCC 480k rising",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["4821"],
                "affected_group_ids": [],
                "evidence_ids": ["SENS_SCC_4821_NEW"],
                "recommendations": [{"action": "Vet check", "priority": "high", "role": "vet"}],
            }
        ])

        from web_cabinet.ai.context import FarmContext

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=_live_settings()),
            patch(f"{_SCANNER_MOD}.build_farm_context", return_value=FarmContext("demo-farm-v1")),
            patch(f"{_SCANNER_MOD}.get_active_insights", return_value=existing),
            patch(f"{_SCANNER_MOD}.get_client", return_value=self._make_claude_client(new_insight_content)),
            patch(f"{_SCANNER_MOD}.save_insight"),
        ):
            results = scan_for_new_insights("demo-farm-v1")

        assert results == [], f"Expected 0 insights (7-day dedup), got {len(results)}"

    def test_scanner_dedup_allows_old_insights(self):
        """Same cow+category older than 7 days is NOT deduped — new insight allowed."""
        existing = [
            {
                "insight_id": "ins_old",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["4821"],
                "evidence_ids": ["SENS_SCC_4821_STALE"],
                "generated_at_utc": (datetime.utcnow() - timedelta(days=10)).isoformat(),
                "title": "Stale SCC insight",
            }
        ]

        new_insight_content = json.dumps([
            {
                "insight_id": "ins_new002x",
                "title": "Fresh SCC spike",
                "description": "SCC 510k",
                "category": "health",
                "priority": "high",
                "affected_cow_ids": ["4821"],
                "affected_group_ids": [],
                "evidence_ids": ["SENS_SCC_4821_FRESH"],
                "recommendations": [{"action": "Vet check", "priority": "high", "role": "vet"}],
            }
        ])

        from web_cabinet.ai.context import FarmContext

        with (
            patch(f"{_SCANNER_MOD}.get_ai_settings", return_value=_live_settings()),
            patch(f"{_SCANNER_MOD}.build_farm_context", return_value=FarmContext("demo-farm-v1")),
            patch(f"{_SCANNER_MOD}.get_active_insights", return_value=existing),
            patch(f"{_SCANNER_MOD}.get_client", return_value=self._make_claude_client(new_insight_content)),
            patch(f"{_SCANNER_MOD}.save_insight"),
        ):
            results = scan_for_new_insights("demo-farm-v1")

        assert len(results) == 1, f"Expected 1 insight (old enough), got {len(results)}"
