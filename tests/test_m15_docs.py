from __future__ import annotations

from pathlib import Path

import yaml

from qe_platform.feedback import FeedbackKind


GUIDE = Path("docs/Trace 与反馈 API 指南.md")
README = Path("README.md")
WORKFLOW = Path(".github/workflows/loadtest.yml")
PROCESS = Path("docs/AI应用全链路质量平台开发流程.md")


def test_m15_guide_records_executable_api_cli_and_privacy_contract():
    guide = GUIDE.read_text(encoding="utf-8")

    for name in (
        "QE_TELEMETRY_DATABASE",
        "QE_TELEMETRY_HASH_KEY",
        "QE_TELEMETRY_INGEST_TOKEN",
        "QE_TELEMETRY_RETENTION_DAYS",
        "QE_TELEMETRY_ENDPOINT",
        "telemetry-prune",
        "POST /api/traces",
        "GET /api/traces",
        "GET /api/traces/{trace_id}",
        "POST /api/traces/{trace_id}/feedback",
        "GET /api/feedback",
    ):
        assert name in guide

    assert "30 天" in guide
    assert "明文" in guide
    assert "PostgreSQL" in guide
    assert "NotImplementedError" in guide
    assert "M16" in guide
    assert "M17" in guide
    assert "人工复核" in guide
    assert "回归用例晋级" in guide
    assert "趋势" in guide
    assert "发布验证" in guide
    assert "FastGPT" not in guide


def test_m15_guide_lists_the_delivered_feedback_categories_from_the_model():
    guide = GUIDE.read_text(encoding="utf-8")

    for category in [kind.value for kind in FeedbackKind]:
        assert category in guide
    assert guide.count("| `") >= len(FeedbackKind)


def test_m15_guide_uses_environment_only_secret_examples():
    guide = GUIDE.read_text(encoding="utf-8")

    assert "X-QE-Telemetry-Token: $QE_TELEMETRY_INGEST_TOKEN" in guide
    assert "--token" not in guide
    assert "--api-key" not in guide
    assert "sk-" not in guide
    assert "Bearer " not in guide


def test_m15_trace_example_uses_nested_source_shape():
    guide = GUIDE.read_text(encoding="utf-8")
    example = guide.split("```bash", 1)[1].split("```", 1)[0]
    assert '"source": {"user_fingerprint"' in example
    assert '    "user_fingerprint":' not in example


def test_readme_links_to_trace_feedback_guide_and_keeps_fastgpt_out_of_m15():
    readme = README.read_text(encoding="utf-8")

    assert "docs/Trace 与反馈 API 指南.md" in readme
    trace_section = readme.split("## Trace 与反馈 API", 1)[1].split("\n## ", 1)[0]
    assert "telemetry-prune" in trace_section
    assert "FastGPT" not in trace_section
    assert GUIDE.exists()


def test_ci_runs_m15_telemetry_contract_offline_with_ephemeral_configuration():
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    job = workflow["jobs"]["m15-telemetry-contract"]

    assert job["name"] == "M15 telemetry contract"
    assert job["env"] == {
        "QE_TELEMETRY_DATABASE": "/tmp/m15-telemetry.db",
        "QE_TELEMETRY_HASH_KEY": "m15-ci-ephemeral-hash-key",
        "QE_TELEMETRY_INGEST_TOKEN": "m15-ci-ephemeral-ingest-token",
        "QE_TELEMETRY_RETENTION_DAYS": "30",
    }
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for test_file in (
        "tests/test_telemetry_models.py",
        "tests/test_telemetry_storage.py",
        "tests/test_telemetry_api.py",
        "tests/test_telemetry_cli.py",
        "tests/test_reference_agent_telemetry.py",
        "tests/test_reference_agent_deployment_config.py",
        "tests/test_m15_docs.py",
    ):
        assert test_file in commands

    assert "http://" not in commands
    assert "https://" not in commands
    assert "DIFY_API_KEY" not in workflow_text
    assert "OPENAI_API_KEY" not in workflow_text
    assert "sk-" not in workflow_text
    assert "FastGPT" not in commands


def test_milestone_status_records_m15_delivery_evidence_and_remaining_boundaries():
    process = PROCESS.read_text(encoding="utf-8")

    row = next(line for line in process.splitlines() if line.startswith("| 15. Trace 存储与反馈 API |"))
    assert "已完成（本机类生产交付）" in row
    assert "Trace/反馈" in row
    assert "SQLite" in row
    assert "Reference Agent" in row
    assert "合并后默认" in row
    assert "#53" in row and "v0.2.0-alpha.21" in row
    assert "Smoke `4/4`" in row and "SQLite 完整性 `ok`" in row
    assert "#52" in row and "已关闭" in row
    assert "共享环境读/反馈鉴权" in row
