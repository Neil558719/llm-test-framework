from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Optional

from .models import LoadTestConfig, LoadTestSummary, SampleResult


def percentile(values: Iterable[float], quantile: float) -> Optional[float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * quantile
    low = math.floor(rank)
    high = math.ceil(rank)
    value = ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (rank - low)
    return round(value, 3)


def _distribution(values: Iterable[float]) -> dict[str, Optional[float]]:
    materialized = list(values)
    return {"p50": percentile(materialized, 0.5), "p95": percentile(materialized, 0.95), "p99": percentile(materialized, 0.99)}


def summarize(samples: Iterable[SampleResult], config: LoadTestConfig, *, wall_time_ms: float) -> LoadTestSummary:
    values = list(samples)
    total = len(values)
    succeeded = sum(sample.success for sample in values)
    failed = total - succeeded
    stream_total = total if config.protocol == "sse" else 0
    costs = [sample for sample in values if sample.cost_total is not None]
    currencies = {sample.cost_currency for sample in costs}
    versions = {sample.price_version for sample in costs}
    return LoadTestSummary(
        requested=config.requests, completed=total, succeeded=succeeded, failed=failed, wall_time_ms=round(wall_time_ms, 3),
        throughput_rps=round(total / (wall_time_ms / 1000), 3) if wall_time_ms > 0 else 0.0,
        error_rate=failed / total if total else 0.0,
        rate_429=sum(sample.status_code == 429 for sample in values) / total if total else 0.0,
        stream_interruption_rate=sum(sample.stream_interrupted for sample in values) / stream_total if stream_total else 0.0,
        latency_ms=_distribution(sample.duration_ms for sample in values),
        ttft_ms=_distribution(sample.ttft_ms for sample in values if sample.ttft_ms is not None),
        status_codes=dict(Counter(str(sample.status_code) for sample in values if sample.status_code is not None)),
        errors=dict(Counter(sample.error_type for sample in values if sample.error_type)),
        prompt_tokens=sum(sample.prompt_tokens for sample in values),
        completion_tokens=sum(sample.completion_tokens for sample in values),
        total_tokens=sum(sample.prompt_tokens + sample.completion_tokens for sample in values),
        cost_total=round(sum(float(sample.cost_total) for sample in costs), 12) if costs and len(currencies) <= 1 else None,
        cost_currency=currencies.pop() if len(currencies) == 1 else ("MIXED" if currencies else ""),
        price_version=versions.pop() if len(versions) == 1 else ("MIXED" if versions else ""),
        costed_samples=len(costs),
        cost_complete=bool(values) and len(costs) == len(values),
    )
