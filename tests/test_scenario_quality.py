"""Declared quality is required evidence, with explicit offline evaluator injection."""

import json
from types import SimpleNamespace

import pytest
import yaml

from llmtest import Config, ResponseEnvelope, ToolCall
from llmtest.clients.mock_client import MockLLMClient
from llmtest.clients.openai_client import OpenAIClient
from llmtest.clients.anthropic_client import AnthropicClient
from llmtest.metrics.tracker import tracker
from llmtest.specs import ClaimVerdict, JudgeResult
from qe_platform.reporting import build_run_report, write_html
from qe_platform.scenarios import ScenarioLoadError, load_scenario_text
from qe_platform.v1_gate import run_gate
from qe_platform.workflow_runner import QualityCheckResult, ScenarioRunner
from tests.test_workflow_runner import SequenceAdapter


def scenario(metrics=None, *, conversation=None, **extra):
    return load_scenario_text(yaml.safe_dump({
        "id": "quality", "name": "Quality", "conversation": conversation or [{"user": "final question"}],
        "quality": {"relevance": {"min_score": .8}} if metrics is None else metrics, **extra,
    }))[0]


def run(spec, evaluator=None, responses=None):
    adapter = SequenceAdapter(responses or [ResponseEnvelope(answer="final answer", sources=["actual source"])])
    return ScenarioRunner(lambda setup: adapter, quality_evaluator=evaluator).run(spec)


@pytest.mark.parametrize("status,score,complete,passed", [
    ("passed", .9, True, True), ("failed", .1, True, False),
    ("inconclusive", None, False, False), ("error", None, False, False),
    ("not_executed", None, False, False),
])
def test_required_quality_controls_complete_and_passed(status, score, complete, passed):
    spec = scenario()
    result = run(spec, lambda s, r: [QualityCheckResult("relevance", {"min_score": .8}, status, score)])
    assert result.complete is complete
    assert result.passed is passed
    check = result.quality_checks[0]
    assert check.required is True and check.threshold == .8
    assert build_run_report([result]).gate_passed is passed


def test_without_evaluator_is_blocked_even_when_environment_says_real(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("implicit provider lookup")
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setattr("llmtest.registry.get_default_client", forbidden)
    result = ScenarioRunner(lambda setup: SequenceAdapter([ResponseEnvelope(answer="ok")])).run(scenario())
    assert not result.passed and not result.complete
    assert result.quality_checks[0].status == "not_executed"
    assert result.quality_checks[0].reason == "evaluator_not_configured"


@pytest.mark.parametrize("metrics", [
    {"unknown": {"min_score": .8}}, {"hallucination_rate": {"max_rate": .2}},
    {"relevance": {}}, {"relevance": {"max_rate": .2}},
    {"relevance": {"min_score": .8, "optional": True}},
    {"hallucination": {"max_rate": .2, "min_score": .8}},
    {"relevance": {"min_score": True}}, {"relevance": {"min_score": "0.8"}},
    {"relevance": {"min_score": -.01}}, {"relevance": {"min_score": 1.01}},
    {"relevance": {"min_score": float("nan")}}, {"hallucination": {"max_rate": float("inf")}},
    {"faithfulness": {"min_score": None}},
])
def test_loader_rejects_invalid_quality(metrics):
    with pytest.raises(ScenarioLoadError) as error:
        scenario(metrics)
    assert "quality" in error.value.path


class RecordingJudge:
    provider = "offline-fixture"
    name = "recording-judge"

    def __init__(self, score=80, maximum=100, claims=None):
        self.score, self.maximum = score, maximum
        self.claims = ["claim"] if claims is None else claims
        self.calls = []

    def judge(self, answer, spec, context, question):
        self.calls.append(("judge", answer, spec, context, question))
        return JudgeResult(self.score, self.maximum, "fixture reasoning", spec.name)

    def extract_claims(self, answer):
        self.calls.append(("extract", answer))
        return self.claims

    def verify_claim(self, claim, context):
        self.calls.append(("verify", claim, context))
        return ClaimVerdict(claim, "SUPPORTED")


def evaluate(spec, response, client):
    from qe_platform.workflow_runner.quality import evaluate_scenario_quality
    return evaluate_scenario_quality(spec, response, client)


@pytest.mark.parametrize("metric", ["accuracy", "relevance", "faithfulness", "helpfulness"])
@pytest.mark.parametrize("raw,expected", [(79, "failed"), (80, "passed"), (100, "passed")])
def test_judge_threshold_is_normalized_without_changing_core_scale(metric, raw, expected, monkeypatch):
    def no_gold(*args, **kwargs):
        pytest.fail("a rubric is not a gold correctness label")
    monkeypatch.setattr(tracker, "add_gold_result", no_gold)
    client = RecordingJudge(raw)
    spec = scenario({metric: {"min_score": .8}}, conversation=[{"user": "first"}, {"user": "actual final question"}])
    response = ResponseEnvelope(answer="actual answer", sources=["actual context 1", "actual context 2"])
    check = evaluate(spec, response, client)[0]
    assert check.status == expected and check.score == raw / 100 and check.threshold == .8
    assert check.provider == "offline-fixture" and check.model == "recording-judge" and check.version
    call = client.calls[0]
    assert call[1] == "actual answer" and call[2].scale == 100 and call[2].min_score == 80
    assert call[3] == "actual context 1\nactual context 2" and call[4] == "actual final question"


@pytest.mark.parametrize("metric", ["faithfulness", "hallucination"])
@pytest.mark.parametrize("sources", [[], ["", "  "]])
def test_missing_grounding_is_inconclusive_without_a_call(metric, sources):
    client = RecordingJudge()
    key = "max_rate" if metric == "hallucination" else "min_score"
    check = evaluate(scenario({metric: {key: .5}}), ResponseEnvelope(answer="answer", sources=sources), client)[0]
    assert check.status == "inconclusive" and check.score is None and check.reason == "missing_grounding_context"
    assert client.calls == []


def test_hallucination_without_claims_preserves_a02_none_and_blocks():
    spec = scenario({"hallucination": {"max_rate": .2}})
    client = RecordingJudge(claims=[])
    result = run(spec, lambda s, r: evaluate(s, r, client))
    assert not result.passed and not result.complete
    assert result.quality_checks[0].status == "inconclusive" and result.quality_checks[0].score is None
    assert len(client.calls) == 1


@pytest.mark.parametrize("failure_at", ["factory", "first", "later"])
def test_interrupted_execution_never_evaluates_an_earlier_response(failure_at):
    called = []
    spec = scenario(conversation=[{"user": "first"}, {"user": "second"}])
    def callback(s, r):
        called.append(r)
        return []
    def factory(setup):
        if failure_at == "factory":
            raise RuntimeError("factory failed")
        return SequenceAdapter(([ResponseEnvelope(answer="earlier")] if failure_at == "later" else []) + [RuntimeError("execution stopped")])
    result = ScenarioRunner(factory, quality_evaluator=callback).run(spec)
    assert called == [] and not result.passed and not result.complete
    assert len(result.quality_checks) == 1 and result.quality_checks[0].status == "not_executed"
    assert result.quality_checks[0].reason == "execution_incomplete"


@pytest.mark.parametrize("damage", ["missing", "duplicate", "unknown", "expectation", "status", "score-none", "score-bool", "score-nan", "score-range", "status-conflict", "required", "threshold", "not-list", "exception", "mutation"])
def test_callback_cannot_redefine_required_declarations_or_create_green(damage):
    def callback(spec, response):
        check = QualityCheckResult("relevance", {"min_score": .8}, "passed", .9)
        if damage == "missing": return []
        if damage == "duplicate": return [check, check]
        if damage == "unknown": check.metric = "other"
        if damage == "expectation": check.expectation = {"min_score": .1}
        if damage == "status": check.status = "not_applicable"
        if damage == "score-none": check.score = None
        if damage == "score-bool": check.score = True
        if damage == "score-nan": check.score = float("nan")
        if damage == "score-range": check.score = 1.1
        if damage == "status-conflict": check.score = .1
        if damage == "required": check.required = False
        if damage == "threshold": check.threshold = .1
        if damage == "not-list": return {"relevance": check}
        if damage == "exception": raise RuntimeError("secret credential must not enter report")
        if damage == "mutation":
            spec.quality.metrics.clear()
            response.answer = "tampered"
            return []
        return [check]
    spec = scenario()
    result = run(spec, callback)
    assert not result.passed and not result.complete
    assert len(result.quality_checks) == 1
    assert result.quality_checks[0].metric == "relevance" and result.quality_checks[0].status == "error"
    assert result.quality_checks[0].required is True and result.quality_checks[0].threshold == .8
    assert result.quality_checks[0].reason
    assert spec.quality.metrics == {"relevance": {"min_score": .8}}
    assert result.steps[0].response.answer == "final answer"
    assert "secret credential" not in json.dumps(result.as_dict())


def test_explicit_mock_is_visible_offline_and_deterministic_failures_stay_failed():
    client = MockLLMClient(Config(mode="mock", mock_latency_ms=0))
    spec = scenario({"helpfulness": {"min_score": 0}}, expect={"response": {"contains": ["missing"]}})
    result = run(spec, lambda s, r: evaluate(s, r, client))
    assert result.complete and not result.passed
    assert result.quality_checks[0].provider == "mock"


def test_programmatic_gate_passes_evaluator_and_default_stays_blocked(tmp_path):
    assets = tmp_path / "quality.yaml"
    assets.write_text("id: q\nname: Q\nconversation: [{user: hi}]\nquality: {relevance: {min_score: 0.8}}\n", encoding="utf-8")
    def callback(s, r):
        return [QualityCheckResult("relevance", {"min_score": .8}, "passed", .9)]
    assert run_gate(asset_dir=assets, json_path=tmp_path / "blocked.json", html_path=tmp_path / "blocked.html") == 1
    assert run_gate(asset_dir=assets, json_path=tmp_path / "pass.json", html_path=tmp_path / "pass.html", quality_evaluator=callback) == 0
    payload = json.loads((tmp_path / "pass.json").read_text(encoding="utf-8"))
    assert payload["scenarios"][0]["quality_checks"][0]["required"] is True


def test_html_expands_escaped_differences_quality_reasons_and_trace(tmp_path):
    response = ResponseEnvelope(answer="wrong", trace_id="<trace>", tool_calls=[ToolCall("tool", {"key": "<actual>"})], metadata={"state": "<actual>"})
    spec = scenario(expect={"tools": [{"name": "tool", "arguments": {"key": "<expected>"}}], "business_state": [{"path": "metadata.state", "value": "<expected>"}]})
    result = run(spec, responses=[response])
    text = write_html(build_run_report([result]), tmp_path / "report.html").read_text(encoding="utf-8")
    for value in ("&lt;trace&gt;", "&lt;actual&gt;", "&lt;expected&gt;", "evaluator_not_configured", "relevance", "not_executed"):
        assert value in text
    assert "<trace>" not in text and "<actual>" not in text


@pytest.mark.parametrize("mixed", [False, True])
def test_runner_cannot_delegate_ungrounded_checks_to_callback(mixed):
    metrics = {"faithfulness": {"min_score": .8}, "hallucination": {"max_rate": .2}}
    if mixed:
        metrics["relevance"] = {"min_score": .8}
    called = []
    def callback(spec, response):
        called.append(set(spec.quality.metrics))
        return [QualityCheckResult(name, threshold, "passed", 0 if name == "hallucination" else 1)
                for name, threshold in spec.quality.metrics.items()]
    result = run(scenario(metrics), callback, [ResponseEnvelope(answer="no source")])
    assert called == ([{"relevance"}] if mixed else [])
    assert not result.passed and not result.complete
    assert all(item.status == "inconclusive" and item.score is None for item in result.quality_checks if item.metric != "relevance")


def test_json_rubric_accuracy_is_explicit_and_does_not_create_gold_accuracy():
    result = run(scenario({"accuracy": {"min_score": .8}}),
                 lambda s, r: [QualityCheckResult("accuracy", {"min_score": .8}, "passed", .9, "legacy message")])
    payload = build_run_report([result]).as_dict()
    check = payload["scenarios"][0]["quality_checks"][0]
    assert check["score_kind"] == "judge_rubric"
    assert check["message"] == "legacy message"
    assert "gold_accuracy" not in payload and "accuracy" not in payload


@pytest.mark.parametrize("score,maximum", [(True, 100), ("80", 100), (float("nan"), 100), (float("inf"), 100), (101, 100), (0, 100), (4, 5), (80, 0), (80, float("inf"))])
def test_malformed_judge_score_is_error_without_tracker_pollution(score, maximum, monkeypatch):
    recorded = []
    monkeypatch.setattr(tracker, "add_judge", recorded.append)
    checks = evaluate(scenario(), ResponseEnvelope(answer="answer"), RecordingJudge(score, maximum))
    assert checks[0].status == "error" and checks[0].score is None
    assert recorded == []


@pytest.mark.parametrize("metric", ["accuracy", "relevance", "faithfulness", "helpfulness", "hallucination"])
@pytest.mark.parametrize("threshold", [0, 1])
def test_quality_threshold_endpoints(metric, threshold):
    key = "max_rate" if metric == "hallucination" else "min_score"
    check = evaluate(scenario({metric: {key: threshold}}), ResponseEnvelope(answer="claim", sources=["claim"]), RecordingJudge(100))[0]
    assert check.status == "passed" and check.threshold == threshold
    assert check.score == (0 if metric == "hallucination" else 1)


@pytest.mark.parametrize("threshold,status", [(.49, "failed"), (.5, "passed"), (.51, "passed")])
def test_hallucination_threshold_uses_max_rate_not_support_rate(threshold, status):
    class MixedJudge(RecordingJudge):
        def verify_claim(self, claim, context):
            return ClaimVerdict(claim, "SUPPORTED" if claim == "supported" else "NOT_SUPPORTED")
    check = evaluate(scenario({"hallucination": {"max_rate": threshold}}), ResponseEnvelope(answer="answer", sources=["source"]),
                     MixedJudge(claims=["supported", "invented"]))[0]
    assert check.score == .5 and check.status == status


@pytest.mark.parametrize("metric", ["relevance", "hallucination"])
def test_explicit_falsey_client_never_uses_default_registry(metric, monkeypatch):
    class FalseyJudge(RecordingJudge):
        def __bool__(self): return False
    def forbidden(*args, **kwargs):
        pytest.fail("default registry must not be used")
    monkeypatch.setattr("llmtest.judge.evaluator.get_default_client", forbidden)
    monkeypatch.setattr("llmtest.hallucination.detector.get_default_client", forbidden)
    key = "max_rate" if metric == "hallucination" else "min_score"
    assert evaluate(scenario({metric: {key: .8}}), ResponseEnvelope(answer="answer", sources=["context"]), FalseyJudge())[0].status == "passed"


def test_evaluator_exception_is_controlled_and_does_not_hide_other_checks():
    class PartialJudge(RecordingJudge):
        def judge(self, answer, spec, context, question):
            if spec.name == "accuracy":
                raise RuntimeError("secret credential")
            return super().judge(answer, spec, context, question)
    checks = evaluate(scenario({"accuracy": {"min_score": .8}, "relevance": {"min_score": .8}}), ResponseEnvelope(answer="answer"), PartialJudge())
    assert [check.status for check in checks] == ["error", "passed"]
    assert "secret credential" not in json.dumps([check.as_dict() for check in checks])


def test_helper_without_client_does_not_select_mock_or_real(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("implicit client lookup")
    monkeypatch.setenv("LLM_MODE", "real")
    monkeypatch.setattr("llmtest.judge.evaluator.get_default_client", forbidden)
    monkeypatch.setattr("llmtest.hallucination.detector.get_default_client", forbidden)
    checks = evaluate(scenario(), ResponseEnvelope(answer="answer"), None)
    assert checks[0].status == "not_executed"


def test_runner_evaluates_once_using_final_executed_question_and_response():
    client = RecordingJudge()
    spec = scenario(conversation=[{"user": "earlier question"}, {"user": "final question"}])
    result = run(spec, lambda s, r: evaluate(s, r, client), [ResponseEnvelope(answer="earlier", sources=["earlier source"]), ResponseEnvelope(answer="final", sources=["final source"])])
    assert result.passed and result.complete
    assert len(client.calls) == 1
    assert client.calls[0][1] == "final" and client.calls[0][3:] == ("final source", "final question")


@pytest.mark.parametrize("claims", ["claim", "", ("claim",), [""], ["  "], [1], [None], [True], [{}]])
def test_explicit_client_rejects_malformed_extracted_claims(claims):
    client = RecordingJudge(claims=claims)
    check = evaluate(scenario({"hallucination": {"max_rate": 0}}), ResponseEnvelope(answer="answer", sources=["context"]), client)[0]
    assert check.status == "error" and check.score is None
    assert not any(call[0] == "verify" for call in client.calls)


@pytest.mark.parametrize("field,value", [
    ("verdict", "UNKNOWN"), ("verdict", ["SUPPORTED"]),
    ("confidence", float("nan")), ("confidence", True), ("confidence", float("inf")),
    ("confidence", -.1), ("confidence", 1.1), ("confidence", "1"),
    ("claim", "different claim"), ("claim", 1), ("evidence", None), ("evidence", []),
])
def test_explicit_client_rejects_malformed_verdict_evidence(field, value):
    class MalformedJudge(RecordingJudge):
        def verify_claim(self, claim, context):
            verdict = ClaimVerdict(claim, "SUPPORTED", 1.0, "actual evidence")
            setattr(verdict, field, value)
            return verdict
    result = run(scenario({"hallucination": {"max_rate": 0}}), lambda s, r: evaluate(s, r, MalformedJudge()))
    assert result.quality_checks[0].status == "error" and result.quality_checks[0].score is None
    assert not result.passed and not result.complete


def test_explicit_client_legal_empty_claims_stays_inconclusive():
    client = RecordingJudge(claims=[])
    check = evaluate(scenario({"hallucination": {"max_rate": 0}}), ResponseEnvelope(answer="answer", sources=["context"]), client)[0]
    assert check.status == "inconclusive" and check.score is None and check.reason == "no_factual_claims"
    assert [call[0] for call in client.calls] == ["extract"]


@pytest.mark.parametrize("client_type,default_model", [(OpenAIClient, "gpt-4o-mini"), (AnthropicClient, "claude-sonnet-5")])
@pytest.mark.parametrize("metric", ["relevance", "hallucination"])
def test_evaluator_records_model_after_current_measurement(client_type, default_model, metric, monkeypatch):
    client = client_type(Config(mode="real"))
    calls = []
    content = ({"score": 90, "reasoning": "local fake"} if metric == "relevance" else ["claim"])
    def create(**params):
        calls.append(params)
        if metric == "hallucination":
            payload = ["claim"] if len(calls) % 2 else {"verdict": "SUPPORTED", "confidence": 1, "evidence": "context"}
        else:
            payload = content
        text = json.dumps(payload)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                               content=[SimpleNamespace(type="text", text=text)])
    # Replace the lazy SDK factory entirely: no SDK import, network or provider call.
    factory = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), messages=SimpleNamespace(create=create))
    monkeypatch.setattr(client, "_get_client", lambda: factory)
    key = "max_rate" if metric == "hallucination" else "min_score"
    spec = scenario({metric: {key: .8}})
    response = ResponseEnvelope(answer="answer", sources=["context"])
    first = evaluate(spec, response, client)[0]
    assert first.status == "passed" and first.model == default_model
    assert first.provider == client.provider and first.version
    assert calls[-1]["model"] == first.model
    client.config.model = "current-model"
    second = evaluate(spec, response, client)[0]
    assert second.status == "passed" and second.model == "current-model"
    assert calls[-1]["model"] == second.model


def test_failed_measurement_does_not_reuse_previous_model(monkeypatch):
    client = RecordingJudge()
    client.last_model_version = SimpleNamespace(model="previous-model", provider="previous-provider")
    def fail(*args, **kwargs):
        raise RuntimeError("failed before a current measurement")
    monkeypatch.setattr(client, "judge", fail)
    check = evaluate(scenario(), ResponseEnvelope(answer="answer"), client)[0]
    assert check.status == "error" and check.model == ""