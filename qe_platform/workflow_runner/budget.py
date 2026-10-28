"""Validated execution policy; each run selects one deadline before queuing."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math


def positive_integer(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + ' must be a positive integer')
    return value


def finite_number(value, name, *, allow_zero=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and not (value < 0 if allow_zero else value <= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + ' must be a finite ' + ('nonnegative' if allow_zero else 'positive') + ' number')
    return float(value)


@dataclass(frozen=True)
class ExecutionBudget:
    case_timeout_s: float = 30.0
    max_attempts: int = 1
    cancel_event: asyncio.Event | None = None
    retry_backoff_s: float = 0.0
    cleanup_timeout_s: float = 1.0

    def __post_init__(self):
        finite_number(self.case_timeout_s, 'case_timeout_s')
        positive_integer(self.max_attempts, 'max_attempts')
        finite_number(self.retry_backoff_s, 'retry_backoff_s', allow_zero=True)
        finite_number(self.cleanup_timeout_s, 'cleanup_timeout_s')
        if self.cancel_event is not None and not isinstance(self.cancel_event, asyncio.Event):
            raise ValueError('cancel_event must be an asyncio.Event')

    def policy(self, max_concurrency=4):
        positive_integer(max_concurrency, 'max_concurrency')
        return {'schema_version': 'async-case-v1', 'case_timeout_s': float(self.case_timeout_s),
                'max_attempts': self.max_attempts, 'retry_backoff_s': float(self.retry_backoff_s),
                'cleanup_timeout_s': float(self.cleanup_timeout_s), 'max_concurrency': max_concurrency,
                'retry_rule': 'explicit_idempotent_and_retryable'}