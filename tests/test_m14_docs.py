from pathlib import Path


GUIDE = Path("docs/Dify 兼容性测试指南.md")
README = Path("README.md")
WORKFLOW = Path(".github/workflows/loadtest.yml")
PROCESS = Path("docs/AI应用全链路质量平台开发流程.md")


def test_m14_guide_documents_safe_environment_only_usage_and_limits():
    guide = GUIDE.read_text(encoding="utf-8")

    assert "DIFY_BASE_URL" in guide
    assert "DIFY_API_KEY" in guide
    assert "dify-compat-gate" in guide
    assert "不支持" in guide
    assert "streaming_ttft" in guide
    assert "--api-key" not in guide
    assert "FastGPT" not in guide


def test_readme_links_to_the_platform_dify_compatibility_guide():
    readme = README.read_text(encoding="utf-8")

    assert "docs/Dify 兼容性测试指南.md" in readme
    assert "docs/Dify 部署与迁移指南.md" not in readme
    assert GUIDE.exists()


def test_ci_runs_only_the_offline_dify_compatibility_contract():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Dify compatibility contract" in workflow
    assert "tests/test_dify_adapter_config.py" in workflow
    assert "tests/test_dify_adapter.py" in workflow
    assert "tests/test_dify_gate.py" in workflow
    assert "DIFY_API_KEY" not in workflow
    assert "api.dify.ai" not in workflow


def test_milestone_status_records_m14_implementation_and_pending_delivery_lifecycle():
    process = PROCESS.read_text(encoding="utf-8")

    row = next(line for line in process.splitlines() if line.startswith("| 14. Dify 适配扩展 |"))
    assert "实现完成（交付进行中）" in row
    assert "Issue [#49]" in row
    assert "DifyChatAdapter" in row
    assert "PR、Actions、审查、合并、Release、部署" in row
