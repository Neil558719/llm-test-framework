from __future__ import annotations

import json

from qe_platform.feedback import FeedbackInput, FeedbackKind, ReviewAttribution, ReviewPriority, ReviewStatus
from qe_platform.quality_loop.cli import main
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import SQLiteTelemetryRepository
from tests.test_quality_loop_models import _report_payload
from tests.test_telemetry_storage import trace_at


def _create_promotion(database):
    telemetry = SQLiteTelemetryRepository(database, hash_key="test-key")
    telemetry.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    feedback = telemetry.add_feedback(FeedbackInput(FeedbackKind.HALLUCINATION, "reporter", "ui"), "trace-1")
    review = telemetry.upsert_review(
        feedback.feedback_id,
        "reviewer",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.MODEL,
        ReviewPriority.HIGH,
    )
    return telemetry.create_promotion(
        review.review_id,
        "vpn-recovery-regression",
        "id: vpn-recovery-regression\nname: VPN recovery\nconversation:\n  - user: hello\n",
    )


def test_quality_loop_cli_runs_import_link_trends_and_validation(tmp_path):
    database = tmp_path / "telemetry.db"
    promotion = _create_promotion(database)
    baseline = _report_payload(run_id="run-baseline", release_id="alpha-22", version="old", started_at="2026-08-28T00:00:00Z", finished_at="2026-08-28T00:00:02Z")
    candidate = _report_payload(run_id="run-candidate", release_id="alpha-23", version="new")
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    assert main(["import-run", "--database", str(database), "--report", str(baseline_path), "--source-label", "fixture"]) == 0
    assert main(["import-run", "--database", str(database), "--report", str(candidate_path), "--source-label", "fixture"]) == 0
    assert main(["link", "--database", str(database), "--promotion-id", promotion.promotion_id, "--offline-run-id", "run-candidate"]) == 0

    trend_json = tmp_path / "trends.json"
    trend_html = tmp_path / "trends.html"
    assert main(["trends", "--database", str(database), "--json", str(trend_json), "--html", str(trend_html)]) == 0
    assert trend_json.exists() and trend_html.exists()
    assert "trace-1" in trend_json.read_text(encoding="utf-8")

    validation_json = tmp_path / "validation.json"
    validation_html = tmp_path / "validation.html"
    assert main([
        "validate-release", "--database", str(database), "--baseline", "run-baseline", "--candidate", "run-candidate",
        "--json", str(validation_json), "--html", str(validation_html), "--max-low-quality-rate-increase", "1.0",
    ]) == 0
    assert json.loads(validation_json.read_text(encoding="utf-8"))["passed"] is True

    strict_json = tmp_path / "strict.json"
    strict_html = tmp_path / "strict.html"
    assert main([
        "validate-release", "--database", str(database), "--baseline", "run-baseline", "--candidate", "run-candidate",
        "--json", str(strict_json), "--html", str(strict_html),
    ]) == 1
    assert json.loads(strict_json.read_text(encoding="utf-8"))["passed"] is False


def test_quality_loop_cli_rejects_missing_report(tmp_path):
    assert main(["import-run", "--database", str(tmp_path / "db"), "--report", str(tmp_path / "missing.json"), "--source-label", "fixture"]) == 2
