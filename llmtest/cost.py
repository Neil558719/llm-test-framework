from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
import json
import math

from .specs import CostMetrics, TokenUsage


@dataclass(frozen=True)
class Price:
    input_per_1k: float
    output_per_1k: float
    currency: str = "USD"
    version: str = ""


class PriceTable:
    """Provider/model price table. Missing prices remain explicitly unknown."""

    def __init__(self, prices: Mapping[str, Price]):
        for key, price in prices.items():
            if not all(math.isfinite(value) and value >= 0 for value in (price.input_per_1k, price.output_per_1k)):
                raise ValueError(f"invalid non-negative finite price for {key!r}")
        self.prices = dict(prices)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Mapping[str, Any]]) -> "PriceTable":
        return cls({str(key): Price(float(value.get("input_per_1k", value.get("input_cost_per_1k", 0))), float(value.get("output_per_1k", value.get("output_cost_per_1k", 0))), str(value.get("currency", "USD")), str(value.get("version", value.get("price_version", "")))) for key, value in mapping.items()})

    @classmethod
    def from_json(cls, value: str | None) -> "PriceTable":
        if not value:
            return cls.from_mapping({})
        try:
            payload = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("LLM_PRICING_TABLE must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("LLM_PRICING_TABLE must be a JSON object")
        return cls.from_mapping(payload)

    def calculate(self, usage: TokenUsage, *, provider: str, model: str) -> Optional[CostMetrics]:
        price = self.prices.get(f"{provider}/{model}") or self.prices.get(model)
        if price is None:
            return None
        input_cost = usage.prompt_tokens / 1000 * price.input_per_1k
        output_cost = usage.completion_tokens / 1000 * price.output_per_1k
        return CostMetrics(input_cost, output_cost, input_cost + output_cost, price.currency, price.version)
