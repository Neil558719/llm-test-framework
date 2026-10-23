"""Offline regressions for invalid evidence being reported as quality success."""

import json
from types import SimpleNamespace

import pytest

from llmtest.assertions.semantic import assert_semantic_match
from llmtest.clients.anthropic_client import AnthropicClient
from llmtest.clients.openai_client import OpenAIClient
from llmtest.config import Config
from llmtest.hallucination.detector import assert_hallucination_rate, detect_hallucination
from llmtest.metrics.tracker import _Tracker
from llmtest.reporting.html_report import render_report, _append_history, _render_history
from llmtest.specs import ClaimVerdict, HallucinationReport, JudgeResult, JudgeSpec, SemanticResult


@pytest.fixture(params=[OpenAIClient, AnthropicClient], ids=['openai', 'anthropic'])
def client(request, monkeypatch):
    instance = request.param(Config(mode='real'))
    def forbidden(*args, **kwargs):
        pytest.fail('Real SDK/embedding must never be invoked by validity tests')
    monkeypatch.setattr(instance, '_get_client', forbidden)
    monkeypatch.setattr(instance, '_embed', forbidden)
    return instance


def supply(client, monkeypatch, payload):
    # Keep JSON extraction and provider validation real; replace only model I/O.
    monkeypatch.setattr(client, '_complete', lambda *a, **k: json.dumps(payload))


def test_empty_claims_have_no_measured_rate(client, monkeypatch):
    supply(client, monkeypatch, [])
    report = detect_hallucination('Revenue is 999 million.', 'Revenue was not supplied.', client=client)
    assert report.hallucination_rate is None
    assert report.support_rate is None
    assert report.contradiction_rate is None
    assert report.status == 'inconclusive'
    assert report.reason
    assert report.as_dict()['status'] == 'inconclusive'


def test_empty_claims_block_required_assertion(client, monkeypatch):
    supply(client, monkeypatch, [])
    with pytest.raises(Exception) as caught:
        assert_hallucination_rate('Revenue is 999 million.', '', client=client, max_rate=0)
    from llmtest.evaluation import EvaluationInconclusiveError
    assert isinstance(caught.value, EvaluationInconclusiveError)


@pytest.mark.parametrize('payload', [
    {'equivalent': 'false', 'score': .9},
    {'equivalent': 1, 'score': .9},
    {'score': .9}, {'equivalent': True},
    {'equivalent': True, 'score': float('nan')},
    {'equivalent': True, 'score': float('inf')},
    {'equivalent': True, 'score': 1.01},
    {'equivalent': False, 'score': -.01},
    {'equivalent': True, 'score': '0.9'},
    {'equivalent': True, 'score': True},
    {'equivalent': False, 'score': .99},
    {'equivalent': True, 'score': .1}, [],
])
def test_invalid_semantic_json_is_rejected_without_embedding_fallback(client, monkeypatch, payload):
    supply(client, monkeypatch, payload)
    with pytest.raises(ValueError):
        client.semantic_equivalent('actual', 'expected')


@pytest.mark.parametrize('payload', [
    {}, {'score': '80'}, {'score': True}, {'score': 0}, {'score': 101},
    {'score': float('nan')}, {'score': float('inf')}, {'score': -float('inf')}, [],
])
def test_invalid_judge_scores_are_rejected_not_clamped(client, monkeypatch, payload):
    supply(client, monkeypatch, payload)
    with pytest.raises(ValueError):
        client.judge('answer', JudgeSpec.helpfulness())


@pytest.mark.parametrize('payload', [
    {}, {'verdict': 'unknown', 'confidence': .8},
    {'verdict': 'supported', 'confidence': .8},
    {'verdict': 'SUPPORTED'}, {'verdict': 'SUPPORTED', 'confidence': '0.8'},
    {'verdict': 'SUPPORTED', 'confidence': float('nan')},
    {'verdict': 'SUPPORTED', 'confidence': float('inf')},
    {'verdict': 'SUPPORTED', 'confidence': 1.1},
    {'verdict': 'SUPPORTED', 'confidence': -.1}, [],
])
def test_invalid_claim_verdicts_are_rejected(client, monkeypatch, payload):
    supply(client, monkeypatch, payload)
    with pytest.raises(ValueError):
        client.verify_claim('claim', 'context')


@pytest.mark.parametrize('payload', [{}, ['claim', 7], [''], [None], 'claim'])
def test_invalid_claim_extraction_cannot_fall_back_to_sentences(client, monkeypatch, payload):
    supply(client, monkeypatch, payload)
    with pytest.raises(ValueError):
        client.extract_claims('claim')


def test_valid_provider_results_and_factual_rate_are_preserved(client, monkeypatch):
    supply(client, monkeypatch, {'equivalent': False, 'score': .2, 'reasoning': 'different'})
    assert client.semantic_equivalent('a', 'b').equivalent is False
    supply(client, monkeypatch, {'score': 80, 'reasoning': 'helpful'})
    assert client.judge('answer', JudgeSpec.helpfulness()).normalized == .8
    supply(client, monkeypatch, {'verdict': 'SUPPORTED', 'confidence': 0, 'evidence': 'source'})
    assert client.verify_claim('claim', 'source').confidence == 0
    report = HallucinationReport(claims=[ClaimVerdict('a', 'SUPPORTED'), ClaimVerdict('b', 'NOT_SUPPORTED')])
    assert report.hallucination_rate == .5


def test_negative_semantic_conclusion_cannot_pass_relaxed_threshold():
    client = SimpleNamespace(semantic_equivalent=lambda *a: SemanticResult(False, .6))
    with pytest.raises(AssertionError):
        assert_semantic_match('a', 'b', client=client, threshold=.5)


def test_helpfulness_score_is_not_gold_accuracy():
    tracker = _Tracker()
    tracker.begin('helpfulness', 'helpfulness')
    tracker.add_judge(JudgeResult(90, 100, spec_name='helpfulness'))
    summary = tracker.summarize()
    assert summary.accuracy is None
    assert summary.mean_judge_score == .9
    assert summary.evaluated_count == 1


def test_gold_accuracy_requires_explicit_boolean_denominator():
    tracker = _Tracker()
    tracker.begin('gold', 'gold')
    tracker.add_gold_result(True)
    tracker.add_gold_result(False)
    tracker.add_gold_result(True)
    with pytest.raises(ValueError):
        tracker.add_gold_result('false')
    summary = tracker.summarize()
    assert summary.accuracy == pytest.approx(2 / 3)
    assert summary.gold_count == 3


def test_non_factual_policy_excludes_empty_reports_from_denominator(client, monkeypatch):
    supply(client, monkeypatch, [])
    report = detect_hallucination('Hello!', '', client=client, no_claims_policy='not_applicable')
    assert report.status == 'not_applicable'
    assert report.reason
    tracker = _Tracker()
    rec = tracker.begin('mixed', 'mixed')
    tracker.add_hallucination(report)
    tracker.add_hallucination(HallucinationReport())
    tracker.add_hallucination(HallucinationReport(claims=[ClaimVerdict('x', 'NOT_SUPPORTED')]))
    assert rec.hallucination_rate == 1
    summary = tracker.summarize()
    assert summary.hallucination_rate == 1
    assert summary.inconclusive_count == 1
    assert summary.not_applicable_count == 1
    assert summary.evaluated_count == 1


def test_html_preserves_empty_evaluation_reason_and_correct_score_label():
    tracker = _Tracker()
    rec = tracker.begin('empty', 'empty')
    tracker.add_hallucination(HallucinationReport())
    tracker.add_judge(JudgeResult(90, 100, spec_name='helpfulness'))
    rendered = render_report(tracker.summarize(), [rec])
    assert 'inconclusive' in rendered
    assert rec.hallucination_reports[0].reason in rendered
    assert 'Judge 均分' in rendered
    assert 'deprecated' in rendered
    assert '金标' in rendered
    assert '聚合为准确率' not in rendered
    assert '归一化得分（得分/满分），聚合为 Judge 均分' in rendered


def test_error_with_partial_claims_renders_without_a_rate():
    tracker = _Tracker()
    rec = tracker.begin('partial', 'partial')
    tracker.add_hallucination(HallucinationReport(
        claims=[ClaimVerdict('a', 'SUPPORTED')], status='error', reason='verification interrupted',
    ))
    rendered = render_report(tracker.summarize(), [rec])
    assert 'verification interrupted' in rendered
    assert '无可用幻觉率' in rendered
    assert tracker.summarize().evaluation_error_count == 1
    assert tracker.summarize().evaluated_count == 0


def test_judge_oversized_integer_is_a_controlled_output_error(client, monkeypatch):
    supply(client, monkeypatch, {'score': 10 ** 400})
    with pytest.raises(ValueError):
        client.judge('answer', JudgeSpec.helpfulness())


def test_mean_judge_score_weights_evaluations_not_test_container():
    tracker = _Tracker()
    tracker.begin('two', 'two')
    tracker.add_judge(JudgeResult(100, 100))
    tracker.add_judge(JudgeResult(100, 100))
    tracker.begin('one', 'one')
    tracker.add_judge(JudgeResult(1, 100))
    assert tracker.summarize().mean_judge_score == pytest.approx(.67)
    assert tracker.summarize().evaluated_count == 3


def test_history_migrates_legacy_judge_mean_without_inventing_gold_accuracy(tmp_path):
    legacy = [{'accuracy': .9, 'passed': 1, 'total': 1}]
    (tmp_path / 'history.json').write_text(json.dumps(legacy), encoding='utf-8')
    tracker = _Tracker()
    tracker.begin('new', 'new')
    tracker.add_gold_result(False)
    tracker.add_judge(JudgeResult(80, 100))
    history = _append_history(str(tmp_path), tracker.summarize(), 'offline')
    assert history[0] == legacy[0]
    assert history[1]['evaluation_schema'] == 2
    assert history[1]['mean_judge_score'] == .8
    assert history[1]['accuracy'] == 0
    rendered = _render_history(legacy)
    assert '<td>—</td><td>90%</td>' in rendered


def test_malformed_json_never_turns_into_a_semantic_result(client, monkeypatch):
    monkeypatch.setattr(client, '_complete', lambda *a, **k: 'not JSON')
    with pytest.raises(ValueError):
        client.semantic_equivalent('a', 'b')


def test_invalid_fact_judge_records_error_and_propagates(client, monkeypatch):
    import importlib
    detector = importlib.import_module('llmtest.hallucination.detector')
    tracker = _Tracker()
    rec = tracker.begin('error', 'error')
    monkeypatch.setattr(detector, 'tracker', tracker)
    values = iter([['claim'], {'verdict': 'UNKNOWN', 'confidence': 1}])
    monkeypatch.setattr(client, '_complete', lambda *a, **k: json.dumps(next(values)))
    with pytest.raises(ValueError):
        detector.assert_hallucination_rate('claim', 'context', client=client)
    assert rec.hallucination_reports[0].status == 'error'
    assert tracker.summarize().evaluation_error_count == 1
    assert tracker.summarize().hallucination_rate is None