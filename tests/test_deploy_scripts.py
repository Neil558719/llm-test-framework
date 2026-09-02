from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_deployment_scripts_are_repeatable_and_document_required_checks():
    smoke = (ROOT / "deploy" / "smoke.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "deploy" / "rollback.ps1").read_text(encoding="utf-8")
    backup = (ROOT / "deploy" / "backup.ps1").read_text(encoding="utf-8")
    assert "set -eu" in smoke
    assert "/api/health" in smoke and "/api/chat" in smoke
    assert "IMAGE_TAG" in rollback
    assert "reference_agent.db" in backup


def test_smoke_script_validates_health_payload_instead_of_only_http_success():
    smoke = (ROOT / "deploy" / "smoke.ps1").read_text(encoding="utf-8")

    assert '$response.status -eq "ok"' in smoke


def test_rollback_waits_for_container_health_before_returning():
    rollback = (ROOT / "deploy" / "rollback.ps1").read_text(encoding="utf-8")

    assert "up -d --no-build --wait" in rollback
