"""Anthropic pricing per million tokens, USD; verified 2026-05.
Revisit quarterly via https://www.anthropic.com/pricing
"""

PRICES_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_create": 3.75},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.00, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00,  "cache_read": 0.10, "cache_create": 1.25},
}


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Return call cost in USD. Unknown model -> 0.0 (do not raise)."""
    rates = PRICES_USD_PER_MTOK.get(model)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_creation_tokens * rates["cache_create"]
        + cache_read_tokens * rates["cache_read"]
    ) / 1_000_000
