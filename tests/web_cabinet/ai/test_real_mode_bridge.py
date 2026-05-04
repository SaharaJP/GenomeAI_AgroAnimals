"""Integration test: _build_bridge_context builds FarmContext in non-demo mode."""
from types import SimpleNamespace


def test_build_bridge_context_returns_farm_context():
    """_build_bridge_context must return FarmContext with farm_id set, no Claude call needed."""
    from web_cabinet.ai.context import _build_bridge_context, FarmContext

    ctx = _build_bridge_context("FARM_001")

    assert isinstance(ctx, FarmContext)
    assert ctx.farm_id == "FARM_001"
    assert isinstance(ctx.recent_events, list)
    assert isinstance(ctx.attention_cows, list)


def test_build_farm_context_routes_to_bridge_when_not_demo():
    """build_farm_context with GENOMEAI_AI_DEMO_MODE=False must call bridge path."""
    from web_cabinet.ai.context import build_farm_context, FarmContext

    settings = SimpleNamespace(GENOMEAI_AI_DEMO_MODE=False)
    ctx = build_farm_context("FARM_001", settings=settings)

    assert isinstance(ctx, FarmContext)
    assert ctx.farm_id == "FARM_001"
