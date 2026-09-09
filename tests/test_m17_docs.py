from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_m17_guide_documents_full_quality_loop_without_fastgpt():
    guide = (ROOT / "docs" / "趋势、线上离线关联与发布验证指南.md").read_text(encoding="utf-8")
    for value in ("quality-loop", "/api/quality/trends", "/api/quality/links", "/api/quality/release-validations", "Trace", "Feedback", "Review", "Promotion", "scenario_id", "SQLite"):
        assert value in guide
    assert "FastGPT" in guide
    assert "真实供应商" in guide


def test_m17_ci_contract_is_offline_and_ephemeral():
    workflow = (ROOT / ".github" / "workflows" / "loadtest.yml").read_text(encoding="utf-8")
    assert "m17-quality-loop-contract" in workflow
    assert "tests/test_quality_loop_contract.py" in workflow
    assert "/tmp/m17" in workflow
    assert "https://" not in workflow.split("m17-quality-loop-contract", 1)[1].split("\n  ", 1)[0]


def test_m17_status_records_delivery_closeout():
    process = (ROOT / "docs" / "AI应用全链路质量平台开发流程.md").read_text(encoding="utf-8")
    row = next(line for line in process.splitlines() if line.startswith("| 17. 趋势、线上离线关联与发布验证 |"))
    assert "已完成" in row
    assert "本机类生产交付" in row
    assert "Issue #58" in row or "Issue [#58]" in row
