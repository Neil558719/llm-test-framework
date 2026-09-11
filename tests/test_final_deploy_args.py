from pathlib import Path
import json
import subprocess
import shutil
import os

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("script", ["migrate.ps1", "backup.ps1", "rollback.ps1", "restore.ps1"])
def test_powershell_operations_preserve_ordered_production_compose_files(tmp_path, script):
    executable = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not executable:
        pytest.skip("PowerShell unavailable")
    log = tmp_path / "docker-args.json"
    driver = tmp_path / "driver.ps1"
    extra = " -ImageTag candidate -ImageDigest sha256:fixture" if script == "rollback.ps1" else ""
    if script == "restore.ps1":
        backup = tmp_path / "input.db"
        backup.write_bytes(b"fixture")
        Path(str(backup) + ".manifest.json").write_text("{}")
        extra = " -BackupPath '" + str(backup).replace("'", "''") + "'"
    driver.write_text(
        "function global:docker { ConvertTo-Json -InputObject @($args) -Compress | Set-Content -LiteralPath '" + str(log).replace("'", "''") + "' -Encoding utf8; $global:LASTEXITCODE = 77 }\n"
        + "& '" + str(ROOT / "deploy" / script).replace("'", "''") + "' -ComposeFiles @('docker-compose.yml', 'docker-compose.production.yml') -ReportPath '" + str(tmp_path / "report.json").replace("'", "''") + "'" + extra,
        encoding="utf-8-sig")
    subprocess.run([executable, "-NoProfile", "-File", str(driver)], cwd=ROOT, capture_output=True, timeout=20)
    assert log.is_file(), "script must invoke Compose with the selected file list"
    arguments = json.loads(log.read_text(encoding="utf-8-sig"))
    assert arguments[:5] == ["compose", "-f", "docker-compose.yml", "-f", "docker-compose.production.yml"]


@pytest.mark.parametrize("script", ["migrate.sh", "backup.sh", "restore.sh"])
def test_shell_operations_preserve_compose_file_order(tmp_path, script):
    import os
    import shutil
    shell = Path(shutil.which("git") or "").parent.parent / "bin" / "bash.exe"
    executable = str(shell) if shell.is_file() else shutil.which("sh")
    if not executable:
        pytest.skip("POSIX shell unavailable")
    docker = tmp_path / "docker"
    docker.write_text("#!/usr/bin/env sh\nprintf '%s\\n' \"$COMPOSE_FILE\" > \"$ARGS_LOG\"\nexit 77\n")
    docker.chmod(0o755)
    log = tmp_path / "args.txt"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"], ARGS_LOG=log.as_posix(),
               REPORT_PATH=(tmp_path / "report.json").as_posix(), BACKUP_DIR=tmp_path.as_posix())
    env.pop("COMPOSE_FILE", None)
    env.pop("COMPOSE_PATH_SEPARATOR", None)
    args = [executable, str(ROOT / "deploy" / script)]
    if script == "restore.sh":
        backup = tmp_path / "input.db"
        backup.write_bytes(b"fixture")
        Path(str(backup) + ".manifest.json").write_text("{}")
        args.append(backup.as_posix())
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, timeout=20)
    assert result.returncode != 0
    assert log.read_text().strip() == "docker-compose.yml:docker-compose.production.yml"


def test_effective_production_compose_preserves_image_secrets_and_auth_mode(tmp_path):
    executable = shutil.which("docker")
    if not executable:
        pytest.skip("Docker Compose CLI unavailable")
    empty = tmp_path / "empty.env"
    empty.write_text("")
    env = dict(os.environ, COMPOSE_FILE="docker-compose.yml;docker-compose.production.yml", COMPOSE_PATH_SEPARATOR=";",
               REFERENCE_AGENT_IMAGE="example.invalid/agent", REFERENCE_AGENT_IMAGE_DIGEST="sha256:" + "1" * 64,
               OIDC_ISSUER="https://idp.example.test", OIDC_AUDIENCE="api", OIDC_CLIENT_ID="browser",
               OIDC_REDIRECT_URI="https://app.example.test/auth/callback", OIDC_JWKS_URL="https://idp.example.test/jwks")
    for name in ("AUTH_SESSION_SECRET_FILE", "QE_TELEMETRY_HASH_KEY_FILE", "QE_TELEMETRY_INGEST_TOKEN_FILE", "REFERENCE_AGENT_MODEL_API_KEY_FILE"):
        secret = tmp_path / name
        secret.write_text("")
        env[name] = str(secret)
    result = subprocess.run([executable, "compose", "--env-file", str(empty), "config", "--format", "json"], cwd=ROOT, env=env, capture_output=True, timeout=30)
    assert result.returncode == 0, "production Compose config must validate"
    service = json.loads(result.stdout)["services"]["reference-agent"]
    assert service["image"] == "example.invalid/agent@sha256:" + "1" * 64
    assert not service.get("build")
    assert service["environment"]["QE_ENVIRONMENT"] == "production"
    assert service["environment"]["AUTH_SESSION_SECRET_FILE"] == "/run/secrets/auth_session_secret"
    assert service["environment"].get("REFERENCE_AGENT_MODEL_API_KEY") in (None, "")
    assert len(service["secrets"]) == 4
