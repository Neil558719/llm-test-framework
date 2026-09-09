from pathlib import Path

import yaml


GUIDE = Path("docs/人工复核与回归晋级指南.md")
README = Path("README.md")
WORKFLOW = Path(".github/workflows/loadtest.yml")
PROCESS = Path("docs/AI应用全链路质量平台开发流程.md")


def test_m16_guide_documents_structured_review_and_promotion_boundary():
    guide = GUIDE.read_text(encoding="utf-8")
    for text in (
        "POST /api/feedback/{feedback_id}/review",
        "GET /api/reviews",
        "POST /api/reviews/{review_id}/promote",
        "GET /api/promotions/{promotion_id}",
        "confirmed",
        "attribution",
        "priority",
        "scenario_yaml",
        "ScenarioRunner",
        "脱敏",
        "M17",
    ):
        assert text in guide
    assert "Bearer " not in guide
    assert "sk-" not in guide
    assert "FastGPT" not in guide


def test_readme_links_to_m16_and_m17_guides():
    readme = README.read_text(encoding="utf-8")
    assert "docs/人工复核与回归晋级指南.md" in readme
    assert "docs/趋势、线上离线关联与发布验证指南.md" in readme


def test_ci_runs_m16_contract_with_ephemeral_configuration():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["m16-review-promotion-contract"]
    assert job["name"] == "M16 review and promotion contract"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for test_file in (
        "tests/test_feedback_review_models.py",
        "tests/test_feedback_promotion.py",
        "tests/test_telemetry_review_storage.py",
        "tests/test_telemetry_review_api.py",
        "tests/test_m16_docs.py",
    ):
        assert test_file in commands
    assert "https://" not in commands
    assert "DIFY_API_KEY" not in commands
    assert "FastGPT" not in commands


def test_status_table_records_m16_scope_and_tracks_m17_state():
    process = PROCESS.read_text(encoding="utf-8")
    row = next(line for line in process.splitlines() if line.startswith("| 16. 人工复核与回归晋级 |"))
    assert "交付进行中" in row or "已完成" in row
    assert "复核" in row and "YAML" in row and "离线" in row
    m17 = next(line for line in process.splitlines() if line.startswith("| 17. 趋势、线上离线关联与发布验证 |"))
    assert any(value in m17 for value in ("未开始", "进行中", "已完成"))
