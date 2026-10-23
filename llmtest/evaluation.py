"""Evaluation validity and strict decoding of real Judge output.

Malformed evidence is an error; absent evidence is inconclusive. Neither is
an affirmative quality result, and neither may silently fall back to embeddings.
"""

from __future__ import annotations

import math
from typing import Literal

EvaluationStatus = Literal['passed', 'failed', 'inconclusive', 'error', 'not_applicable']
SEMANTIC_EQUIVALENCE_THRESHOLD = 0.7


class EvaluationInconclusiveError(RuntimeError):
    """A required check has no evidence from which to reach a conclusion."""


class EvaluationOutputError(ValueError):
    """Real Judge output violates the evaluation contract."""


def _object(raw):
    if not isinstance(raw, dict):
        raise EvaluationOutputError('Judge output must be a JSON object')
    return raw


def _number(value, name: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float):
        raise EvaluationOutputError(f'{name} must be a finite JSON number')
    try:
        number = float(value)
    except OverflowError as exc:
        raise EvaluationOutputError(f'{name} must be a finite JSON number') from exc
    if not math.isfinite(number):
        raise EvaluationOutputError(f'{name} must be a finite JSON number')
    if not minimum <= value <= maximum:
        raise EvaluationOutputError(f'{name} must be in [{minimum}, {maximum}]')
    return number


def _text(raw, name: str) -> str:
    value = raw.get(name, '')
    if not isinstance(value, str):
        raise EvaluationOutputError(f'{name} must be a JSON string')
    return value


def parse_semantic(raw):
    from .specs import SemanticResult

    raw = _object(raw)
    equivalent = raw.get('equivalent')
    if type(equivalent) is not bool:
        raise EvaluationOutputError('equivalent must be a JSON boolean')
    score = _number(raw.get('score'), 'score', 0, 1)
    if equivalent != (score >= SEMANTIC_EQUIVALENCE_THRESHOLD):
        raise EvaluationOutputError('equivalent contradicts score at threshold 0.7')
    return SemanticResult(equivalent, score, _text(raw, 'reasoning'))


def parse_judge(raw, spec):
    from .specs import JudgeResult

    raw = _object(raw)
    scale = _number(spec.scale, 'scale', 1, float('inf'))
    score = _number(raw.get('score'), 'score', 1, scale)
    return JudgeResult(score, scale, _text(raw, 'reasoning'), spec.name)


def parse_claims(raw):
    if not isinstance(raw, list) or any(not isinstance(c, str) or not c.strip() for c in raw):
        raise EvaluationOutputError('claims must be an array of non-empty JSON strings')
    return [c.strip() for c in raw]


def parse_verdict(raw, claim: str):
    from .specs import ClaimVerdict, SUPPORTED, NOT_SUPPORTED, CONTRADICTED

    raw = _object(raw)
    verdict = raw.get('verdict')
    if verdict not in (SUPPORTED, NOT_SUPPORTED, CONTRADICTED):
        raise EvaluationOutputError('verdict must be SUPPORTED, NOT_SUPPORTED or CONTRADICTED')
    confidence = _number(raw.get('confidence'), 'confidence', 0, 1)
    return ClaimVerdict(claim, verdict, confidence, _text(raw, 'evidence'))