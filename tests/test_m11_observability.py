import json

from llmtest import CostMetrics, ModelVersion, ResponseEnvelope, TokenUsage
from llmtest.cost import PriceTable
from llmtest.config import Config
from llmtest.clients.mock_client import MockLLMClient
from qe_platform.reporting import build_run_report, write_html
from qe_platform.workflow_runner import ScenarioRunResult, StepResult
from reference_agent.app import create_app
from fastapi.testclient import TestClient


def test_price_table_calculates_cost_and_unknown_price_is_explicit():
    table = PriceTable.from_mapping({"deepseek/deepseek-chat": {
        "input_per_1k": 0.001, "output_per_1k": 0.002,
        "currency": "USD", "version": "2026-01"
    }})
    cost = table.calculate(TokenUsage(1000, 500), provider="deepseek", model="deepseek-chat")
    assert cost == CostMetrics(0.001, 0.001, 0.002, "USD", "2026-01")
    assert table.calculate(TokenUsage(1, 1), provider="x", model="y") is None


def test_mock_client_exposes_usage_and_model_version_after_completion():
    client = MockLLMClient(Config(mode="mock", model="mock-v2"))
    client.complete([{"role": "user", "content": "hello"}])
    assert client.last_usage is not None
    assert client.last_usage.total_tokens > 0
    assert client.last_model_version == ModelVersion(provider="mock", model="mock-v2")


def test_response_envelope_round_trips_cost_and_version():
    envelope = ResponseEnvelope(
        answer="ok", usage=TokenUsage(10, 5),
        model_version=ModelVersion("deepseek", "deepseek-chat", prompt="p1", knowledge_base="kb1", tools="t1"),
        cost=CostMetrics(0.01, 0.02, 0.03, "USD", "v1"),
    )
    payload = envelope.as_dict()
    assert payload["model_version"]["model"] == "deepseek-chat"
    assert payload["cost"]["total"] == 0.03
    assert ResponseEnvelope.from_dict(payload).cost.total == 0.03


def test_reference_agent_includes_observability_fields():
    client = TestClient(create_app(":memory:", model_client=MockLLMClient(Config(mode="mock", model="mock-v1"))))
    response = client.post("/api/chat", json={"message": "如何重置密码？", "user_id": "U1001"})
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"]["provider"] == "mock"
    assert body["usage"]["total_tokens"] > 0
    assert body["cost"] is None


def test_reference_agent_calculates_configured_model_cost_and_asset_versions(monkeypatch):
    monkeypatch.setenv("LLM_PRICING_TABLE", json.dumps({"mock/mock-v1": {
        "input_per_1k": 1, "output_per_1k": 2, "version": "price-1"
    }}))
    cost = PriceTable.from_json(__import__("os").environ["LLM_PRICING_TABLE"]).calculate(
        __import__("llmtest").TokenUsage(10, 5), provider="mock", model="mock-v1"
    )
    assert cost.total > 0 and cost.price_version == "price-1"


def test_html_report_mentions_usage_cost_and_model(tmp_path):
    result = ScenarioRunResult("s1", "Scenario", "fixture.yaml", "session", "2026-01-01T00:00:00Z", expected_step_count=1)
    response = ResponseEnvelope(answer="ok", usage=TokenUsage(2, 3), model_version=ModelVersion("mock", "mock-v1"), cost=CostMetrics(0.1, 0.2, 0.3))
    result.steps.append(StepResult(0, "hello", "passed", response))
    result.finished_at = "2026-01-01T00:00:01Z"
    report = build_run_report([result], run_id="r1")
    html = write_html(report, tmp_path / "report.html").read_text(encoding="utf-8")
    assert "mock-v1" in html and "0.3" in html and "Token" in html
