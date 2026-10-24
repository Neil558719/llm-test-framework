"""Explicit scenario-to-llmtest quality integration; never selects a provider."""

from copy import deepcopy
from dataclasses import replace
import math

from llmtest import JudgeSpec, ResponseEnvelope, __version__, detect_hallucination, llm_judge
from llmtest.evaluation import parse_claims, parse_verdict
from llmtest.specs import ClaimVerdict, JudgeResult
from qe_platform.scenarios.models import QUALITY_THRESHOLDS, QualityExpectation, ScenarioSpec, validate_quality_metrics

from .models import QualityCheckResult


def pending_quality(metrics, reason="evaluator_not_configured", *, status="not_executed"):
    validate_quality_metrics(metrics)
    return [QualityCheckResult(metric, deepcopy(expectation), status=status,
                               threshold=expectation[QUALITY_THRESHOLDS[metric]], reason=reason)
            for metric, expectation in metrics.items()]


def _number(value, minimum=0, maximum=1):
    return type(value) in (int, float) and minimum <= value <= maximum and math.isfinite(value)


def validate_callback_results(metrics, values):
    """Bind results to declarations; never trust callback coverage or policy changes."""
    if not isinstance(values, list) or any(not isinstance(value, QualityCheckResult) for value in values):
        raise ValueError("invalid_evaluator_results")
    names = [value.metric for value in values]
    if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names) or set(names) != set(metrics):
        raise ValueError("invalid_evaluator_metrics")
    by_name = {value.metric: value for value in values}
    checks = []
    for metric, expectation in metrics.items():
        value = by_name[metric]
        threshold = expectation[QUALITY_THRESHOLDS[metric]]
        validate_quality_metrics({metric: value.expectation})
        if value.required is not True or value.expectation != expectation:
            raise ValueError("evaluator_changed_policy")
        if value.threshold is not None and (not _number(value.threshold) or value.threshold != threshold):
            raise ValueError("evaluator_changed_threshold")
        if value.status not in ("passed", "failed", "inconclusive", "error", "not_executed"):
            raise ValueError("invalid_evaluator_status")
        if value.status in ("passed", "failed"):
            if not _number(value.score):
                raise ValueError("invalid_evaluator_score")
            passed = value.score <= threshold if metric == "hallucination" else value.score >= threshold
            if passed != (value.status == "passed"):
                raise ValueError("evaluator_score_status_conflict")
        elif value.score is not None:
            raise ValueError("unavailable_evaluation_has_score")
        if any(not isinstance(getattr(value, key), str) for key in ("message", "reason", "provider", "model", "version")):
            raise ValueError("invalid_evaluator_metadata")
        checks.append(replace(value, expectation=deepcopy(expectation), threshold=threshold,
                              reason=value.reason or "evaluator_" + value.status,
                              provider=value.provider or "callback"))
    return checks


def run_quality_callback(scenario, response, metrics, evaluator):
    checks = pending_quality(metrics)
    eligible = deepcopy(metrics)
    if not "\n".join(response.sources or []).strip():
        for check in checks:
            if check.metric in ("faithfulness", "hallucination"):
                check.status, check.reason = "inconclusive", "missing_grounding_context"
                del eligible[check.metric]
    if eligible:
        callback_spec = replace(deepcopy(scenario), quality=QualityExpectation(deepcopy(eligible)))
        try:
            values = evaluator(callback_spec, deepcopy(response))
        except Exception:
            evaluated = pending_quality(eligible, "evaluator_error", status="error")
        else:
            try:
                evaluated = validate_callback_results(eligible, values)
            except (ValueError, TypeError):
                evaluated = pending_quality(eligible, "invalid_evaluator_result", status="error")
        by_name = {check.metric: check for check in evaluated}
        checks = [by_name.get(check.metric, check) for check in checks]
    return checks


class _ExplicitClient:
    """Keep even a falsey injected client from falling back to llmtest's registry."""

    def __init__(self, client):
        self.client = client
        self.measured = False

    def __getattr__(self, name):
        return getattr(self.client, name)

    def _measure(self, method, *args):
        value = getattr(self.client, method)(*args)
        self.measured = True
        return value

    def judge(self, answer, spec, context, question):
        measured = self._measure("judge", answer, spec, context, question)
        if (not isinstance(measured, JudgeResult) or not _number(measured.max_score, 1, float("inf"))
                or measured.max_score != spec.scale or not _number(measured.score, 1, measured.max_score)):
            raise ValueError("invalid_judge_score")
        return measured

    def extract_claims(self, answer):
        return parse_claims(self._measure("extract_claims", answer))

    def verify_claim(self, claim, context):
        measured = self._measure("verify_claim", claim, context)
        if not isinstance(measured, ClaimVerdict) or not isinstance(measured.claim, str) or measured.claim != claim:
            raise ValueError("invalid_claim_verdict")
        return parse_verdict({"verdict": measured.verdict, "confidence": measured.confidence,
                              "evidence": measured.evidence}, claim)


def evaluate_scenario_quality(scenario: ScenarioSpec, response: ResponseEnvelope, client=None) -> list[QualityCheckResult]:
    """Measure the final response with its final user question and actual sources.

    The runner calls this only after all turns execute. ``version`` identifies
    the llmtest integration, not a provider's unreported model revision.
    """
    checks = pending_quality(scenario.quality.metrics)
    if client is None:
        return checks
    question = scenario.conversation[-1].user
    context = "\n".join(response.sources or [])
    for check in checks:
        explicit = _ExplicitClient(client)
        check.provider = "mock" if getattr(client, "is_mock", False) else getattr(client, "provider", "injected")
        check.version = __version__
        if check.metric in ("faithfulness", "hallucination") and not context.strip():
            check.status, check.reason = "inconclusive", "missing_grounding_context"
            continue
        try:
            if check.metric == "hallucination":
                report = detect_hallucination(response.answer, context, client=explicit)
                if report.hallucination_rate is None:
                    check.status, check.reason = "inconclusive", "no_factual_claims"
                    continue
                check.score = report.hallucination_rate
                passed = check.score <= check.threshold
            else:
                spec = getattr(JudgeSpec, check.metric)(min_score=check.threshold * 100)
                measured = llm_judge(response.answer, spec, client=explicit, context=context, question=question)
                check.score = measured.score / measured.max_score
                passed = check.score >= check.threshold
            check.status = "passed" if passed else "failed"
            check.reason = "threshold_met" if passed else "threshold_not_met"
        except Exception:
            # An injected evaluator is an external boundary; retain a controlled reason only.
            check.status, check.score, check.reason = "error", None, "evaluation_error"
        finally:
            if explicit.measured:
                model_version = getattr(client, "last_model_version", None)
                check.model = getattr(model_version, "model", "") or getattr(client, "name", type(client).__name__)
                if not getattr(client, "is_mock", False):
                    check.provider = getattr(model_version, "provider", "") or check.provider
    return checks