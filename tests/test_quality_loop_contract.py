from __future__ import annotations

import json

from qe_platform.quality_loop.engine import build_quality_links, validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy
from qe_platform.quality_loop.reporting import write_quality_html, write_quality_json
from tests.test_quality_loop_engine import _setup_database
from tests.test_telemetry_storage import utc


def test_complete_trace_feedback_review_promotion_offline_release_contract(tmp_path):
    repository, baseline, candidate = _setup_database(tmp_path)
    validation = validate_release(
        repository,
        baseline.run_id,
        candidate.run_id,
        ReleaseGatePolicy(max_low_quality_rate_increase=1.0),
        now=utc("2026-09-01T00:00:00+00:00"),
        validation_id="contract-validation",
    )
    links = build_quality_links(repository, offline_run_id=candidate.run_id, now=utc("2026-09-01T00:00:00+00:00"))
    evidence = {"validation": validation.as_dict(), "links": [link.as_dict() for link in links]}
    json_path = write_quality_json(evidence, tmp_path / "contract.json")
    html_path = write_quality_html(evidence, tmp_path / "contract.html")
    serialized = json.dumps(evidence, sort_keys=True)
    for value in ("trace-1", "vpn-recovery-regression", "run-candidate", "contract-validation"):
        assert value in serialized
        assert value in html_path.read_text(encoding="utf-8")
    assert "private request" not in json_path.read_text(encoding="utf-8")
    assert validation.passed is True
