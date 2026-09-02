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


def test_deployment_scripts_check_native_command_exit_codes_and_use_stable_volume_name():
    backup = (ROOT / "deploy" / "backup.ps1").read_text(encoding="utf-8")
    rollback = (ROOT / "deploy" / "rollback.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "$LASTEXITCODE" in backup
    assert "$LASTEXITCODE" in rollback
    assert "REFERENCE_AGENT_VOLUME" in compose


def test_compose_does_not_expose_unauthenticated_agent_or_forward_unused_llm_secret():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${REFERENCE_AGENT_PORT:-8000}:8000"' in compose
    assert "LLM_API_KEY" not in compose


def test_smoke_asserts_business_payloads():
    smoke = (ROOT / "deploy" / "smoke.sh").read_text(encoding="utf-8")

    assert "tool_calls" in smoke
    assert "ticket_status" in smoke
    assert "approval_status" in smoke
