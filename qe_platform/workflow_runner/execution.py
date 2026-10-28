"""Strict safe async execution evidence shared by reports and stored readers."""
from __future__ import annotations

from copy import deepcopy

from .budget import ExecutionBudget, finite_number


def validate_execution(value, expected_policy=None, *, expected_step_count=None, steps=None):
    if value is None:
        if expected_policy is not None:
            raise ValueError('controlled async execution evidence is missing')
        return None
    if (not isinstance(value, dict) or not isinstance(value.get('policy'), dict)
            or set(value) != {'policy', 'status', 'effect_unknown', 'attempts', 'stage_ms', 'cleanup_status'}):
        raise ValueError('invalid execution evidence')
    policy = value['policy']
    if expected_policy is None or policy != expected_policy:
        raise ValueError('execution policy differs from controlled manifest')
    try:
        budget = ExecutionBudget(case_timeout_s=policy['case_timeout_s'], max_attempts=policy['max_attempts'],
            retry_backoff_s=policy['retry_backoff_s'], cleanup_timeout_s=policy['cleanup_timeout_s'])
        if policy != budget.policy(policy['max_concurrency']):
            raise ValueError('unknown execution policy')
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid execution policy') from exc
    if value.get('status') not in ('completed', 'deadline', 'cancelled', 'error') or type(value.get('effect_unknown')) is not bool:
        raise ValueError('invalid execution outcome')
    if value.get('cleanup_status') not in ('closed', 'borrowed', 'not_created', 'timeout', 'unresponsive', 'error'):
        raise ValueError('invalid execution cleanup')
    stages = value.get('stage_ms')
    if not isinstance(stages, dict) or set(stages) != {'queue', 'init', 'rate_wait', 'request', 'backoff', 'evaluation', 'cleanup'}:
        raise ValueError('missing execution stages')
    for timing in stages.values():
        finite_number(timing, 'execution timing', allow_zero=True)
    attempts = value.get('attempts')
    if not isinstance(attempts, list):
        raise ValueError('invalid execution attempts')
    if (type(expected_step_count) is not int or expected_step_count <= 0
            or not isinstance(steps, list) or not steps or len(steps) > expected_step_count):
        raise ValueError('execution requires controlled step coverage')
    counts, keys = {}, {}
    terminal = {}
    previous = None
    for attempt in attempts:
        if (not isinstance(attempt, dict) or type(attempt.get('step_index')) is not int or attempt['step_index'] < 0
                or set(attempt) != {'step_index', 'attempt', 'operation_key', 'status', 'effect_unknown'}):
            raise ValueError('invalid execution attempt step')
        index = attempt['step_index']
        if index >= expected_step_count or index >= len(steps):
            raise ValueError('execution attempt is outside controlled steps')
        if previous is None:
            if index != 0:
                raise ValueError('execution attempts omit earlier steps')
        elif index == previous['step_index']:
            if previous['status'] != 'error' or previous['effect_unknown']:
                raise ValueError('retry requires a known failed attempt')
        elif index != previous['step_index'] + 1 or previous['status'] != 'completed':
            raise ValueError('execution attempt order contradicts completed steps')
        counts[index] = counts.get(index, 0) + 1
        if type(attempt.get('attempt')) is not int or attempt['attempt'] != counts[index] or counts[index] > budget.max_attempts:
            raise ValueError('invalid execution attempt count')
        key = attempt.get('operation_key')
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('invalid operation key')
        if index in keys and keys[index] != key:
            raise ValueError('retry changed operation identity')
        keys[index] = key
        if attempt.get('status') not in ('completed', 'error', 'deadline', 'cancelled') or type(attempt.get('effect_unknown')) is not bool:
            raise ValueError('invalid execution attempt outcome')
        if attempt['status'] == 'completed' and attempt['effect_unknown']:
            raise ValueError('completed attempt cannot have an unknown outcome')
        terminal[index] = previous = attempt
    for index, step in enumerate(steps):
        if step['status'] != 'error' and (index not in terminal or terminal[index]['status'] != 'completed'):
            raise ValueError('completed step requires a completed terminal attempt')
    if value['status'] == 'completed' and (len(steps) != expected_step_count or any(step['status'] == 'error' for step in steps)):
        raise ValueError('completed execution contradicts controlled step coverage')
    if any(attempt['effect_unknown'] for attempt in attempts) and not value['effect_unknown']:
        raise ValueError('unknown effects cannot be discarded')
    return deepcopy(value)


def execution_complete(value):
    return value is None or (value['status'] == 'completed' and not value['effect_unknown']
                             and value['cleanup_status'] in ('closed', 'borrowed'))