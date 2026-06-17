"""Per-model token-to-cost lookup.

Prices are USD per 1,000,000 tokens, mid-2026 published rates from OpenAI + Anthropic.
Update as providers change them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float


PRICING: dict[str, ModelPricing] = {
    # OpenAI — https://openai.com/api/pricing/
    "gpt-4o": ModelPricing(2.50, 10.00),
    "gpt-4o-mini": ModelPricing(0.15, 0.60),
    "gpt-4-turbo": ModelPricing(10.00, 30.00),
    "gpt-3.5-turbo": ModelPricing(0.50, 1.50),
    "o1-preview": ModelPricing(15.00, 60.00),
    "o1-mini": ModelPricing(3.00, 12.00),
    # Anthropic — https://www.anthropic.com/pricing
    "claude-3-5-sonnet-latest": ModelPricing(3.00, 15.00),
    "claude-3-5-sonnet": ModelPricing(3.00, 15.00),
    "claude-3-5-haiku-latest": ModelPricing(0.80, 4.00),
    "claude-3-5-haiku": ModelPricing(0.80, 4.00),
    "claude-3-opus-latest": ModelPricing(15.00, 75.00),
    "claude-3-opus": ModelPricing(15.00, 75.00),
    "claude-3-sonnet": ModelPricing(3.00, 15.00),
    "claude-3-haiku": ModelPricing(0.25, 1.25),
}


def compute_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """Return cost in USD for a (model, tokens) pair, or None if model is unknown."""
    if model is None:
        return None
    pricing = PRICING.get(model)
    if pricing is None:
        # Allow "openai/gpt-4o" → "gpt-4o" prefix stripping.
        if "/" in model:
            stripped = model.split("/", 1)[1]
            pricing = PRICING.get(stripped)
        if pricing is None:
            return None
    cost = 0.0
    if prompt_tokens:
        cost += (prompt_tokens / 1_000_000.0) * pricing.input_per_million
    if completion_tokens:
        cost += (completion_tokens / 1_000_000.0) * pricing.output_per_million
    return round(cost, 6)
