from pathlib import Path
import os
import shutil
import subprocess
import time
import uuid

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_remains_valid_for_model_runtime_configuration():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["reference-agent"]["environment"]["REFERENCE_AGENT_MODEL"]


def test_start_script_runs_compose_watch_and_waits_for_health():
    script = (ROOT / "deploy" / "start-reference-agent.ps1").read_text(encoding="utf-8")

    assert "FileSystemWatcher" in script
    assert "WatchOnly" in script
    assert "--force-recreate" in script
    assert "--wait" in script
    assert "/api/health" in script
    assert "Start-Process" in script
    assert "docker compose -f $composePath port reference-agent 8000" in script
    assert "try {" in script and "Invoke-ReferenceAgentRefresh" in script and "catch" in script
    assert "CommandLine" in script and "-WatchOnly" in script
    assert "$pathHash" in script
    assert "process-error.log" in script


def test_startup_task_registration_script_is_idempotent_and_retry_configured():
    script = (ROOT / "deploy" / "register-reference-agent-task.ps1").read_text(encoding="utf-8")

    assert "Register-ScheduledTask" in script
    assert "Unregister-ScheduledTask" in script
    assert "New-ScheduledTaskTrigger" in script
    assert "-AtLogOn" in script
    assert "-User $currentUser" in script
    assert "RestartCount" in script
    assert "RestartInterval" in script
    assert "-LogonType Interactive" in script
    assert "-AllowStartIfOnBatteries" in script
    assert "-DontStopIfGoingOnBatteries" in script
    assert "Start-Sleep" in script
    assert "-Command" in script
    assert "start-reference-agent.ps1" in script
    assert "REFERENCE_AGENT_MODEL_API_KEY" not in script
    assert "-Argument" in script
    assert "CmdletizationQuery_NotFound_TaskName" in script
    assert "Get-ScheduledTask -TaskName $Name -ErrorAction Stop" in script
    assert "throw" in script


def test_readme_documents_logon_registration_and_unregistration():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "register-reference-agent-task.ps1" in readme
    assert "Unregister" in readme
    assert "5 次" in readme


def test_windows_startup_task_registration_is_idempotent_and_removable():
    if os.name != "nt" or shutil.which("powershell.exe") is None:
        import pytest
        pytest.skip("Windows Task Scheduler is required")

    script = ROOT / "deploy" / "register-reference-agent-task.ps1"
    task_name = f"LLMTest startup test {uuid.uuid4()}"
    register = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-TaskName", task_name, "-DelaySeconds", "1",
    ]
    unregister = register[:-2] + ["-Unregister"]
    try:
        subprocess.run(register, check=True, capture_output=True, text=True)
        subprocess.run(register[:-1] + ["2"], check=True, capture_output=True, text=True)
        inspect = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                f"$t=Get-ScheduledTask -TaskName '{task_name}'; $x=Export-ScheduledTask -TaskName '{task_name}'; "
                "[pscustomobject]@{Count=@($t).Count; Xml=$x; Args=$t.Actions[0].Arguments} | ConvertTo-Json -Compress",
            ],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        import json
        task = json.loads(inspect.stdout.lstrip("\ufeff"))
        assert task["Count"] == 1
        assert "<LogonTrigger>" in task["Xml"]
        assert "Start-Sleep -Seconds 2" in task["Xml"]
        assert "<Count>5</Count>" in task["Xml"]
        assert "<Interval>PT1M</Interval>" in task["Xml"]
        assert "API_KEY" not in task["Args"]
        subprocess.run(unregister, check=True, capture_output=True, text=True)
        missing = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"if (Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue) {{ exit 1 }}"],
            check=False, capture_output=True, text=True,
        )
        assert missing.returncode == 0
        subprocess.run(unregister, check=True, capture_output=True, text=True)
    finally:
        subprocess.run(unregister, check=False, capture_output=True, text=True)


def test_windows_watcher_survives_failed_refresh_and_retries_next_env_save(tmp_path, monkeypatch):
    if shutil.which("powershell.exe") is None:
        import pytest
        pytest.skip("Windows PowerShell is required")

    deploy = tmp_path / "deploy"
    deploy.mkdir()
    source = ROOT / "deploy" / "start-reference-agent.ps1"
    (deploy / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  reference-agent:\n    image: test\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("REFERENCE_AGENT_MODEL=one\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_file = tmp_path / "docker-calls.log"
    counter_file = tmp_path / "docker-counter"
    (fake_bin / "docker.ps1").write_text(
        "param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)\n"
        f"Add-Content -LiteralPath '{log_file}' -Value ($Arguments -join ' ') -Encoding utf8\n"
        f"if (-not (Test-Path -LiteralPath '{counter_file}')) {{ Set-Content -LiteralPath '{counter_file}' -Value 1; exit 1 }}\n"
        "exit 0\n",
        # Windows PowerShell 5.1 treats a BOM-less script as the active ANSI
        # code page.  The temporary workspace may contain non-ASCII names.
        encoding="utf-8-sig",
    )
    child_env = os.environ.copy()
    child_env["PATH"] = str(fake_bin) + ";" + child_env["PATH"]
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(deploy / source.name), "-ComposeFile", str(tmp_path / "docker-compose.yml"), "-WatchOnly", "-WaitTimeout", "5"]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_env)
    try:
        time.sleep(1)
        env_file.write_text("REFERENCE_AGENT_MODEL=two\n", encoding="utf-8")
        time.sleep(2)
        env_file.write_text("REFERENCE_AGENT_MODEL=three\n", encoding="utf-8")
        time.sleep(2)
        assert process.poll() is None
        assert log_file.read_text(encoding="utf-8").count("compose") >= 2
    finally:
        process.kill()
        process.wait(timeout=5)


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

    assert "up -d --pull $PullPolicy --no-build --wait" in rollback


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


def test_backup_verifies_sqlite_integrity_before_reporting_success():
    backup = (ROOT / "deploy" / "backup.ps1").read_text(encoding="utf-8")

    assert "PRAGMA integrity_check" in backup
    assert "run --pull $PullPolicy --rm --no-deps" in backup
    assert "up -d --wait" not in backup
    assert "Resolve-Path" in backup


def test_linux_backup_and_restore_scripts_are_available_for_server_migration():
    backup = (ROOT / "deploy" / "backup.sh").read_text(encoding="utf-8")
    restore = (ROOT / "deploy" / "restore.sh").read_text(encoding="utf-8")

    assert "trap" in backup and "PRAGMA integrity_check" in backup
    assert "PRAGMA integrity_check" in restore and 'docker compose up -d --pull "$pull_policy" --wait' in restore
    assert "trap" in restore


def test_ci_restores_backup_and_checks_persisted_session_boundary():
    workflow = (ROOT / ".github" / "workflows" / "container.yml").read_text(encoding="utf-8")

    assert "backup-marker" in workflow
    assert "post-backup-marker" in workflow
    assert "deploy/restore.sh" in workflow
    assert "SELECT session_id FROM sessions" in workflow


def test_smoke_asserts_business_payloads():
    smoke = (ROOT / "deploy" / "smoke.sh").read_text(encoding="utf-8")

    assert "tool_calls" in smoke
    assert "ticket_status" in smoke
    assert "approval_status" in smoke
