"""幻觉检测：事实一致性评估，计算幻觉率。"""

from __future__ import annotations

from typing import List, Union

from ..metrics.tracker import tracker
from ..evaluation import EvaluationInconclusiveError
from ..registry import get_default_client
from ..specs import HallucinationReport


def _to_context(context: Union[str, List[str]]) -> str:
    """归一化上下文：str 原样，list[str] 按段落拼接。"""
    if isinstance(context, str):
        return context
    return "\n".join(str(c) for c in context)


def detect_hallucination(
    response: str,
    context: Union[str, List[str]],
    *,
    client=None,
    no_claims_policy: str = 'inconclusive',
) -> HallucinationReport:
    """检测回答相对上下文的幻觉。

    流程：把回答分解为事实断言 → 逐条核对是否被上下文支撑/矛盾 →
    返回报告（含幻觉率）。测量函数，结果自动记入指标采集。

    空 claims 默认 inconclusive。仅在调用方已确认回复合法且无事实内容时，
    显式指定 no_claims_policy='not_applicable'；该结果无率值且排除分母。
    """
    if no_claims_policy not in ('inconclusive', 'not_applicable'):
        raise ValueError('no_claims_policy must be inconclusive or not_applicable')
    client = client or get_default_client()
    ctx_text = _to_context(context)
    try:
        claims = client.extract_claims(response)
        verdicts = [client.verify_claim(c, ctx_text) for c in claims]
    except Exception as exc:
        tracker.add_hallucination(HallucinationReport(
            response=response, context=ctx_text, status='error',
            reason=f'Evaluation failed: {type(exc).__name__}',
        ))
        raise
    report = HallucinationReport(response=response, context=ctx_text, claims=verdicts)
    if not verdicts and no_claims_policy == 'not_applicable':
        report.status = 'not_applicable'
        report.reason = 'Caller policy permits a non-factual reply; excluded from hallucination metrics.'
    tracker.add_hallucination(report)
    if report.hallucination_rate is not None:
        tracker.record_metric("hallucination_rate", report.hallucination_rate)
    return report


def assert_hallucination_rate(
    response: str,
    context: Union[str, List[str]],
    *,
    client=None,
    max_rate: float = 0.5,
) -> HallucinationReport:
    """断言幻觉率 ≤ max_rate；失败抛 AssertionError，缺证据抛 EvaluationInconclusiveError。

    必需断言不接受空 claims 的 not_applicable 例外；显式例外由测量调用方管理。
    """
    report = detect_hallucination(response, context, client=client)
    rate = report.hallucination_rate
    if rate is None:
        tracker.add_assertion('assert_hallucination_rate', False, report.reason)
        raise EvaluationInconclusiveError(report.reason)
    passed = rate <= max_rate
    report.status = 'passed' if passed else 'failed'

    summary = (
        f"幻觉率 {rate:.1%}（阈值 {max_rate:.1%}）· 断言 {report.total} 条 · "
        f"支持 {len(report.supported)} · 幻觉 {len(report.hallucinated)}"
        f"{'（含矛盾 ' + str(len(report.contradicted)) + '）' if report.contradicted else ''}"
    )
    details = "\n".join(
        f"  [{c.verdict}] {c.claim} —— {c.evidence}" for c in report.claims
    )
    message = f"{summary}\n{details}"

    tracker.add_assertion("assert_hallucination_rate", passed, message, rate, max_rate)
    if not passed:
        raise AssertionError(message)
    return report


__all__ = ["detect_hallucination", "assert_hallucination_rate", "HallucinationReport"]
