from __future__ import annotations

from qe_platform.feedback import FeedbackInput, FeedbackKind, ReviewAttribution, ReviewPriority, ReviewStatus
from qe_platform.quality_loop.engine import build_quality_links, build_trends, quality_summary, validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import SQLiteTelemetryRepository
from tests.test_quality_loop_models import _report_payload
from tests.test_telemetry_storage import trace_at, utc


def _setup_database(tmp_path):
    database = tmp_path / "telemetry.db"
    telemetry = SQLiteTelemetryRepository(database, retention_days=30, hash_key="test-key")
    telemetry.upsert_trace(trace_at("2026-08-29T00:00:00+00:00", application="service-desk"))
    feedback = telemetry.add_feedback(FeedbackInput(FeedbackKind.HALLUCINATION, "reporter", "ui"), "trace-1")
    review = telemetry.upsert_review(
        feedback.feedback_id,
        "reviewer",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.MODEL,
        ReviewPriority.HIGH,
    )
    promotion = telemetry.create_promotion(
        review.review_id,
        "vpn-recovery-regression",
        "id: vpn-recovery-regression\nname: VPN recovery\nconversation:\n  - user: hello\n",
    )
    quality = SQLiteQualityRepository(database, retention_days=30)
    baseline = quality.import_run(
        _report_payload(
            run_id="run-baseline",
            release_id="alpha-22",
            version="old",
            started_at="2026-08-28T00:00:00Z",
            finished_at="2026-08-28T00:00:02Z",
        ),
        source_label="fixture",
    )
    candidate = quality.import_run(
        _report_payload(
            run_id="run-candidate",
            release_id="alpha-23",
            version="new",
        ),
        source_label="fixture",
    )
    quality.create_link(promotion.promotion_id, candidate.run_id, now=utc("2026-09-01T00:00:00+00:00"))
    return quality, baseline, candidate


def test_build_trends_aggregates_online_and_offline_metrics(tmp_path):
    quality, _, _ = _setup_database(tmp_path)
    points = build_trends(quality, now=utc("2026-09-01T00:00:00+00:00"))
    assert len(points) >= 2
    online = next(item for item in points if item.online_trace_count == 1)
    assert online.application == "service-desk"
    assert online.feedback_count == 1
    assert online.confirmed_low_quality_count == 1
    assert online.low_quality_rate == 1.0
    offline = next(item for item in points if item.offline_run_count == 1 and item.version == "new")
    assert offline.offline_pass_rate == 1.0
    assert offline.total_tokens == 20


def test_build_quality_links_returns_only_explicit_relationships(tmp_path):
    quality, _, candidate = _setup_database(tmp_path)
    links = build_quality_links(quality, offline_run_id=candidate.run_id, now=utc("2026-09-01T00:00:00+00:00"))
    assert len(links) == 1
    assert links[0].scenario_id == "vpn-recovery-regression"


def test_validate_release_passes_when_policy_allows_linked_quality_delta(tmp_path):
    quality, baseline, candidate = _setup_database(tmp_path)
    result = validate_release(
        quality,
        baseline.run_id,
        candidate.run_id,
        ReleaseGatePolicy(max_low_quality_rate_increase=1.0),
        now=utc("2026-09-01T00:00:00+00:00"),
        validation_id="validation-pass",
    )
    assert result.passed is True
    assert all(item.passed for item in result.checks)
    assert quality.get_validation("validation-pass") == result


def test_validate_release_fails_failure_rate_and_missing_scenario(tmp_path):
    quality, baseline, _ = _setup_database(tmp_path)
    candidate = quality.import_run(
        _report_payload(
            run_id="run-bad",
            release_id="alpha-23",
            version="bad",
            passed=1,
            failed=1,
            gate_passed=False,
            scenarios=[
                {
                    "scenario_id": "vpn-recovery-regression",
                    "passed": True,
                    "complete": True,
                    "steps": [],
                    "usage": {"total_tokens": 12},
                    "cost": {"total": 0.12, "currency": "USD"},
                    "latency_ms": 120,
                },
                {
                    "scenario_id": "new-scenario",
                    "passed": False,
                    "complete": False,
                    "steps": [],
                    "usage": {"total_tokens": 8},
                    "cost": {"total": 0.08, "currency": "USD"},
                    "latency_ms": 80,
                },
            ],
        ),
        source_label="fixture",
    )
    result = validate_release(
        quality,
        baseline.run_id,
        candidate.run_id,
        ReleaseGatePolicy(),
        now=utc("2026-09-01T00:00:00+00:00"),
        validation_id="validation-fail",
    )
    assert result.passed is False
    failed_names = {item.name for item in result.checks if not item.passed}
    assert {"candidate_complete", "scenario_set", "candidate_failure_rate"} <= failed_names


def test_validate_release_rejects_unknown_runs(tmp_path):
    quality, baseline, _ = _setup_database(tmp_path)
    try:
        validate_release(quality, baseline.run_id, "missing", ReleaseGatePolicy())
    except KeyError as exc:
        assert "run" in str(exc)
    else:
        raise AssertionError("missing candidate run was accepted")


def test_validate_release_enforces_optional_application_and_release_identity(tmp_path):
    quality, baseline, candidate = _setup_database(tmp_path)
    result = validate_release(
        quality,
        baseline.run_id,
        candidate.run_id,
        ReleaseGatePolicy(application="other-agent", release_id="alpha-23"),
        now=utc("2026-09-01T00:00:00+00:00"),
        validation_id="validation-identity",
    )
    assert result.passed is False
    assert any(item.name == "candidate_application" and not item.passed for item in result.checks)


def test_trend_p95_does_not_merge_offline_summary_with_online_samples(tmp_path):
    quality, _, _ = _setup_database(tmp_path)
    quality.import_run(
        _report_payload(
            run_id="offline-same-day",
            release_id="alpha-23",
            version="new",
            started_at="2026-08-29T01:00:00Z",
            finished_at="2026-08-29T01:00:02Z",
            scenarios=[
                {
                    "scenario_id": "ticket-create-vpn",
                    "passed": True,
                    "complete": True,
                    "steps": [],
                    "usage": {"total_tokens": 1},
                    "cost": {"total": 0.01, "currency": "USD"},
                    "latency_ms": 1000,
                },
                {
                    "scenario_id": "vpn-recovery-regression",
                    "passed": True,
                    "complete": True,
                    "steps": [],
                    "usage": {"total_tokens": 1},
                    "cost": {"total": 0.01, "currency": "USD"},
                    "latency_ms": 1000,
                },
            ],
        ),
        source_label="fixture",
    )
    quality.online_rows = lambda **_: [{
        "trace_id": "online-sample",
        "application": "reference-agent",
        "timestamp": "2026-08-29T00:30:00.000000Z",
        "version": "new",
        "latency_ms": 12.5,
        "total_tokens": 0,
        "total_cost": 0.0,
        "feedback_count": 0,
        "confirmed_low_quality_count": 0,
    }]
    points = build_trends(quality, version="new", now=utc("2026-09-01T00:00:00+00:00"))
    point = next(item for item in points if item.bucket == "2026-08-29")
    assert point.p95_latency_ms == 12.5


def test_quality_summary_returns_validation_and_safe_associations(tmp_path):
    quality, baseline, candidate = _setup_database(tmp_path)
    validate_release(
        quality,
        baseline.run_id,
        candidate.run_id,
        ReleaseGatePolicy(max_low_quality_rate_increase=1.0),
        now=utc("2026-09-01T00:00:00+00:00"),
        validation_id="summary-validation",
    )
    summary = quality_summary(quality, "summary-validation", now=utc("2026-09-01T00:00:00+00:00"))
    assert summary["validation"]["validation_id"] == "summary-validation"
    assert summary["candidate"]["run_id"] == candidate.run_id
    assert summary["links"][0]["scenario_id"] == "vpn-recovery-regression"
