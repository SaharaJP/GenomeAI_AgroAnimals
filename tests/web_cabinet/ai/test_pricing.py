"""Tests for AI pricing module."""
from web_cabinet.ai.pricing import compute_cost_usd


def test_sonnet_pricing_basic():
    cost = compute_cost_usd("claude-sonnet-4-6", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 4.50) < 1e-6


def test_opus_pricing_basic():
    cost = compute_cost_usd("claude-opus-4-7", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 22.50) < 1e-6


def test_haiku_pricing_basic():
    cost = compute_cost_usd("claude-haiku-4-5", 1_000_000, 100_000, 0, 0)
    assert abs(cost - 1.50) < 1e-6


def test_cache_tokens_charged_separately():
    # 100K cache_create + 1M cache_read for sonnet:
    # cache_create: 0.1 * 3.75 = 0.375; cache_read: 1.0 * 0.30 = 0.30 → 0.675
    cost = compute_cost_usd("claude-sonnet-4-6", 0, 0, 100_000, 1_000_000)
    assert abs(cost - 0.675) < 1e-6


def test_unknown_model_returns_zero():
    cost = compute_cost_usd("gpt-5-imaginary", 1_000_000, 100_000, 0, 0)
    assert cost == 0.0


def test_empty_call_returns_zero():
    cost = compute_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0)
    assert cost == 0.0
