from __future__ import annotations

from qe_platform.ops.metrics import measured, PROCESS_METRICS

import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import QualityLink, ReleaseCheck, ReleaseGatePolicy, ReleaseValidation, TrendPoint
from .storage import SQLiteQualityRepository


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value.astimezone(timezone.utc)


def _bucket(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def build_trends(
    repository: SQLiteQualityRepository,
    *,
    application: str = "",
    version: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
    now: datetime | None = None,
) -> list[TrendPoint]:
    start = _utc(start)
    end = _utc(end)
    if start is not None and end is not None and end < start:
        raise ValueError("end must not precede start")
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "online_trace_count": 0,
            "feedback_count": 0,
            "confirmed_low_quality_count": 0,
            "offline_run_count": 0,
            "offline_passed": 0,
            "offline_total": 0,
            "online_latencies": [],
            "offline_p95s": [],
            "total_tokens": 0,
            "total_cost": 0.0,
        }
    )

    def include(timestamp: str) -> bool:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        return not ((start is not None and parsed < start) or (end is not None and parsed > end))

    for row in repository.online_rows(now=now):
        if application and row["application"] != application:
            continue
        if version and row["version"] != version:
            continue
        if not include(row["timestamp"]):
            continue
        key = (_bucket(row["timestamp"]), row["application"], row["version"])
        group = groups[key]
        group["online_trace_count"] += 1
        group["feedback_count"] += row["feedback_count"]
        group["confirmed_low_quality_count"] += row["confirmed_low_quality_count"]
        if row["latency_ms"] > 0:
            group["online_latencies"].append(row["latency_ms"])
        group["total_tokens"] += row["total_tokens"]
        group["total_cost"] += row["total_cost"]

    for run in repository.list_runs(application=application, version=version, now=now):
        if not include(run.started_at):
            continue
        key = (_bucket(run.started_at), run.application, run.version)
        group = groups[key]
        group["offline_run_count"] += 1
        group["offline_passed"] += run.passed
        group["offline_total"] += run.total
        if run.p95_latency_ms is not None:
            group["offline_p95s"].append(run.p95_latency_ms)
        group["total_tokens"] += run.total_tokens
        group["total_cost"] += run.total_cost

    values: list[TrendPoint] = []
    for (bucket, app, release_version), group in sorted(groups.items()):
        feedback = group["feedback_count"]
        offline_total = group["offline_total"]
        values.append(
            TrendPoint(
                bucket=bucket,
                application=app,
                version=release_version,
                online_trace_count=group["online_trace_count"],
                feedback_count=feedback,
                confirmed_low_quality_count=group["confirmed_low_quality_count"],
                low_quality_rate=(group["confirmed_low_quality_count"] / feedback) if feedback else None,
                offline_run_count=group["offline_run_count"],
                offline_pass_rate=(group["offline_passed"] / offline_total) if offline_total else None,
                # Raw online samples can be combined into a percentile.  An
                # offline p95 is already a summary, so never mix it into the
                # online sample distribution; expose it only when it is the
                # sole latency source for the bucket.
                p95_latency_ms=(
                    _percentile(group["online_latencies"], 0.95)
                    if group["online_latencies"]
                    else (group["offline_p95s"][0] if len(group["offline_p95s"]) == 1 else None)
                ),
                total_tokens=group["total_tokens"],
                total_cost=group["total_cost"],
            )
        )
    return values


def build_quality_links(
    repository: SQLiteQualityRepository,
    *,
    offline_run_id: str = "",
    promotion_id: str = "",
    now: datetime | None = None,
) -> list[QualityLink]:
    return repository.list_links(offline_run_id=offline_run_id, promotion_id=promotion_id, now=now)


def _linked_low_quality_rate(
    repository: SQLiteQualityRepository,
    run_id: str,
    *,
    now: datetime | None,
) -> float:
    links = repository.list_links(offline_run_id=run_id, now=now)
    if not links:
        return 0.0
    rows = {row["trace_id"]: row for row in repository.online_rows(now=now)}
    feedback = sum(rows[link.trace_id]["feedback_count"] for link in links if link.trace_id in rows)
    low_quality = sum(rows[link.trace_id]["confirmed_low_quality_count"] for link in links if link.trace_id in rows)
    return low_quality / feedback if feedback else 0.0


@measured("quality_gate")
def validate_release(
    repository: SQLiteQualityRepository,
    baseline_run_id: str,
    candidate_run_id: str,
    policy: ReleaseGatePolicy,
    *,
    validation_id: str | None = None,
    now: datetime | None = None,
) -> ReleaseValidation:
    baseline = repository.get_run(baseline_run_id, now=now)
    candidate = repository.get_run(candidate_run_id, now=now)
    if baseline is None:
        raise KeyError("baseline run not found")
    if candidate is None:
        raise KeyError("candidate run not found")
    baseline_pass_rate = baseline.passed / baseline.total if baseline.total else 0.0
    candidate_pass_rate = candidate.passed / candidate.total if candidate.total else 0.0
    candidate_failure_rate = candidate.failed / candidate.total if candidate.total else 1.0
    pass_rate_drop = max(0.0, baseline_pass_rate - candidate_pass_rate)
    low_quality_increase = max(
        0.0,
        _linked_low_quality_rate(repository, candidate_run_id, now=now)
        - _linked_low_quality_rate(repository, baseline_run_id, now=now),
    )
    checks = (
        ReleaseCheck(
            "candidate_application",
            candidate.application,
            policy.application or candidate.application,
            not policy.application or candidate.application == policy.application,
            "candidate application matches policy" if not policy.application or candidate.application == policy.application else "candidate application differs from policy",
        ),
        ReleaseCheck(
            "candidate_release_id",
            candidate.release_id,
            policy.release_id or candidate.release_id,
            not policy.release_id or candidate.release_id == policy.release_id,
            "candidate release ID matches policy" if not policy.release_id or candidate.release_id == policy.release_id else "candidate release ID differs from policy",
        ),
        ReleaseCheck(
            "candidate_complete",
            candidate.gate_passed,
            policy.require_complete,
            (not policy.require_complete) or candidate.gate_passed,
            "candidate offline run is complete" if ((not policy.require_complete) or candidate.gate_passed) else "candidate offline run did not pass its own gate",
        ),
        ReleaseCheck(
            "scenario_set",
            list(candidate.scenario_ids),
            list(baseline.scenario_ids),
            set(candidate.scenario_ids) == set(baseline.scenario_ids),
            "candidate covers the baseline scenario set" if set(candidate.scenario_ids) == set(baseline.scenario_ids) else "candidate scenario set differs from baseline",
        ),
        ReleaseCheck(
            "candidate_failure_rate",
            candidate_failure_rate,
            policy.max_candidate_failure_rate,
            candidate_failure_rate <= policy.max_candidate_failure_rate,
            "candidate failure rate is within policy" if candidate_failure_rate <= policy.max_candidate_failure_rate else "candidate failure rate exceeds policy",
        ),
        ReleaseCheck(
            "pass_rate_drop",
            pass_rate_drop,
            policy.max_pass_rate_drop,
            pass_rate_drop <= policy.max_pass_rate_drop,
            "pass rate did not drop beyond policy" if pass_rate_drop <= policy.max_pass_rate_drop else "pass rate drop exceeds policy",
        ),
        ReleaseCheck(
            "low_quality_rate_increase",
            low_quality_increase,
            policy.max_low_quality_rate_increase,
            low_quality_increase <= policy.max_low_quality_rate_increase,
            "linked online low-quality rate is within policy" if low_quality_increase <= policy.max_low_quality_rate_increase else "linked online low-quality rate increase exceeds policy",
        ),
    )
    result = ReleaseValidation(
        validation_id or str(uuid.uuid4()),
        baseline_run_id,
        candidate_run_id,
        policy,
        all(item.passed for item in checks),
        checks,
        len(repository.list_links(offline_run_id=candidate_run_id, now=now)),
        (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
    )
    saved = repository.save_validation(result)
    PROCESS_METRICS.increment("quality_gate_passed_total" if saved.passed else "quality_gate_denied_total")
    return saved


def quality_summary(
    repository: SQLiteQualityRepository,
    validation_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a safe, navigable release result and its explicit associations."""
    validation = repository.get_validation(validation_id)
    if validation is None:
        raise KeyError("release validation not found")
    baseline = repository.get_run(validation.baseline_run_id, now=now)
    candidate = repository.get_run(validation.candidate_run_id, now=now)
    if baseline is None or candidate is None:
        raise KeyError("release validation references an expired or missing run")
    return {
        "validation": validation.as_dict(),
        "baseline": baseline.as_dict(),
        "candidate": candidate.as_dict(),
        "links": [item.as_dict() for item in repository.list_links(offline_run_id=candidate.run_id, now=now)],
        "trends": [
            item.as_dict()
            for item in build_trends(
                repository,
                application=candidate.application,
                version=candidate.version,
                now=now,
            )
        ],
    }
