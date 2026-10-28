"""Cooperative native async execution with one pre-queue deadline (Python 3.9+)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import uuid

from llmtest import ResponseEnvelope
from qe_platform.adapters.base import AsyncApplicationAdapterError
from qe_platform.contracts import AssertionResult

from .budget import ExecutionBudget, positive_integer
from .models import ScenarioRunResult, StepResult
from .quality import pending_quality, run_async_quality_callback
from .runner import ScenarioRunner


def _async_callable(value):
    return inspect.iscoroutinefunction(value) or inspect.iscoroutinefunction(getattr(value, '__call__', None))


class _BudgetInterrupted(Exception):
    def __init__(self, status):
        self.status = status


def _checkpoint(state):
    if state['result'].execution['status'] != 'running':
        raise asyncio.CancelledError
    if state['cancel_event'] is not None and state['cancel_event'].is_set():
        raise _BudgetInterrupted('cancelled')
    if asyncio.get_running_loop().time() >= state['deadline']:
        raise _BudgetInterrupted('deadline')


@asynccontextmanager
async def _stage(state, name):
    state['stage'] = name
    started = asyncio.get_running_loop().time()
    try:
        yield
    finally:
        state['result'].execution['stage_ms'][name] += (asyncio.get_running_loop().time() - started) * 1000


class AsyncScenarioRunner:
    def __init__(self, adapter_factory, *, max_concurrency=4, limiter=None, quality_evaluator=None, owns_adapter=True):
        self.max_concurrency = positive_integer(max_concurrency, 'max_concurrency')
        if type(owns_adapter) is not bool:
            raise ValueError('owns_adapter must be boolean')
        if limiter is not None and not _async_callable(limiter):
            raise ValueError('limiter must be asynchronous')
        self.adapter_factory, self.limiter = adapter_factory, limiter
        self.quality_evaluator, self.owns_adapter = quality_evaluator, owns_adapter
        self._semaphore = self._loop = None
        self._checker = ScenarioRunner(lambda _: None)

    async def run_many(self, scenarios, *, budget: ExecutionBudget):
        tasks = [asyncio.create_task(self.run(scenario, budget=budget)) for scenario in scenarios]
        try:
            return await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, scenario, *, budget: ExecutionBudget):
        if not isinstance(budget, ExecutionBudget):
            raise ValueError('budget must be an ExecutionBudget')
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget.case_timeout_s
        if self._loop is None:
            self._loop = loop
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
        elif self._loop is not loop:
            raise ValueError('runner must be used on one event loop')
        metrics = deepcopy(scenario.quality.metrics)
        result = ScenarioRunResult(scenario.id, scenario.name, scenario.source,
            scenario.setup.session_id or str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(),
            expected_step_count=len(scenario.conversation), quality_checks=pending_quality(metrics),
            execution={'policy': budget.policy(self.max_concurrency), 'status': 'running', 'effect_unknown': False,
                       'attempts': [], 'stage_ms': dict.fromkeys(('queue', 'init', 'rate_wait', 'request', 'backoff', 'evaluation', 'cleanup'), 0.0),
                       'cleanup_status': 'not_created'})
        state = {'result': result, 'adapter': None, 'acquired': False, 'stage': 'queue', 'active_attempt': None, 'dialogue_started': None,
                 'deadline': deadline, 'cancel_event': budget.cancel_event}
        worker = watcher = None
        externally_cancelled = False
        try:
            if budget.cancel_event is not None and budget.cancel_event.is_set():
                self._abort(scenario, state, 'cancelled')
            else:
                worker = asyncio.create_task(self._work(scenario, state, budget))
                pending = {worker}
                if budget.cancel_event is not None:
                    watcher = asyncio.create_task(budget.cancel_event.wait())
                    pending.add(watcher)
                await asyncio.wait(pending, timeout=max(0, deadline - loop.time()), return_when=asyncio.FIRST_COMPLETED)
                # Cancellation wins a same-tick race; an expired deadline never becomes success.
                if budget.cancel_event is not None and budget.cancel_event.is_set():
                    worker.cancel()
                    self._abort(scenario, state, 'cancelled')
                elif loop.time() >= deadline or not worker.done():
                    worker.cancel()
                    self._abort(scenario, state, 'deadline')
                else:
                    try:
                        worker.result()
                    except _BudgetInterrupted as exc:
                        self._abort(scenario, state, exc.status)
                    except asyncio.CancelledError:
                        self._abort(scenario, state, 'cancelled')
                    except Exception as exc:
                        self._abort(scenario, state, 'error', type(exc).__name__)
        except asyncio.CancelledError:
            externally_cancelled = True
            if worker is not None:
                worker.cancel()
            self._abort(scenario, state, 'cancelled')
        finally:
            # Finite separate teardown allowance, not a fresh request/evaluation budget.
            cleanup = asyncio.create_task(self._cleanup(state, worker, watcher, budget.cleanup_timeout_s))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    externally_cancelled = True
            cleanup.result()
            result.finished_at = datetime.now(timezone.utc).isoformat()
        if externally_cancelled:
            raise asyncio.CancelledError
        return result

    async def _work(self, scenario, state, budget):
        result = state['result']
        async with _stage(state, 'queue'):
            await self._semaphore.acquire()
            state['acquired'] = True
            _checkpoint(state)
        async with _stage(state, 'init'):
            adapter = self.adapter_factory(scenario.setup)
            if inspect.isawaitable(adapter):
                adapter = await adapter
            state['adapter'] = adapter
            _checkpoint(state)
            if not _async_callable(getattr(adapter, 'send', None)):
                raise ValueError('native_async_adapter_required')
        try:
            for index, step in enumerate(scenario.conversation):
                response = await self._send(scenario, state, budget, index)
                step_result = StepResult(index, step.user, 'passed', response=response)
                result.tool_calls.extend(response.tool_calls)
                if step.expect:
                    step_result.assertions = self._checker._check_expectation(step.expect, response)
                    if not all(check.passed for check in step_result.assertions):
                        step_result.status = 'failed'
                result.steps.append(step_result)
        finally:
            if state['dialogue_started'] is not None:
                result.latency_ms = (asyncio.get_running_loop().time() - state['dialogue_started']) * 1000
        final_response = result.steps[-1].response if result.steps else None
        result.final_assertions = self._checker._check_expectation(scenario.expect, final_response, result.tool_calls)
        if scenario.quality.metrics and self.quality_evaluator is not None:
            _checkpoint(state)
            async with _stage(state, 'evaluation'):
                checks = await run_async_quality_callback(scenario, final_response, scenario.quality.metrics, self.quality_evaluator)
                _checkpoint(state)
                result.quality_checks = checks
        state['stage'] = 'finalize'
        _checkpoint(state)
        result.execution['status'] = 'completed'

    async def _send(self, scenario, state, budget, index):
        result, adapter = state['result'], state['adapter']
        operation_key = hashlib.sha256((result.session_id + ':' + str(index)).encode()).hexdigest()
        for number in range(1, budget.max_attempts + 1):
            _checkpoint(state)
            if self.limiter is not None:
                async with _stage(state, 'rate_wait'):
                    await self.limiter()
                    _checkpoint(state)
            if state['dialogue_started'] is None:
                state['dialogue_started'] = asyncio.get_running_loop().time()
            attempt = {'step_index': index, 'attempt': number, 'operation_key': operation_key, 'status': 'started', 'effect_unknown': False}
            result.execution['attempts'].append(attempt)
            state['active_attempt'] = attempt
            try:
                async with _stage(state, 'request'):
                    response = await adapter.send(scenario.conversation[index].user, user_id=scenario.setup.user_id, session_id=result.session_id)
                    _checkpoint(state)
                    if not isinstance(response, ResponseEnvelope):
                        raise ValueError('invalid_async_adapter_response')
            except AsyncApplicationAdapterError as exc:
                attempt['status'], attempt['effect_unknown'] = 'error', exc.effect_unknown
                result.execution['effect_unknown'] |= exc.effect_unknown
                state['active_attempt'] = None
                if not (getattr(adapter, 'retry_safe', False) is True and exc.retryable is True and not exc.effect_unknown and number < budget.max_attempts):
                    raise
                async with _stage(state, 'backoff'):
                    await asyncio.sleep(budget.retry_backoff_s)
            else:
                attempt['status'] = 'completed'
                state['active_attempt'] = None
                return response

    def _abort(self, scenario, state, status, reason=''):
        result = state['result']
        result.execution['status'] = status
        attempt = state['active_attempt']
        if attempt is not None:
            attempt['status'] = status
            # Idempotency does not establish the outcome of an already dispatched request.
            attempt['effect_unknown'] = True
            result.execution['effect_unknown'] |= attempt['effect_unknown']
        if len(result.steps) < result.expected_step_count:
            index = len(result.steps)
            user = scenario.conversation[index].user if index or state['dialogue_started'] is not None else ''
            error = status + ' at ' + state['stage'] + (': ' + reason if reason else '')
            result.steps.append(StepResult(index, user, 'error', error=error))
            result.final_assertions = [AssertionResult('execution', False, error, path='adapter' if user == '' else f'steps[{index}]')]
            if user != '':
                result.final_assertions.extend(self._checker._check_expectation(scenario.expect, None, result.tool_calls, execution_error=error))
            result.quality_checks = pending_quality(scenario.quality.metrics, 'execution_incomplete')
        elif scenario.quality.metrics:
            result.quality_checks = pending_quality(scenario.quality.metrics, status + '_during_' + state['stage'])

    async def _cleanup(self, state, worker, watcher, allowance):
        loop = asyncio.get_running_loop()
        end = loop.time() + allowance
        result = state['result']
        async with _stage(state, 'cleanup'):
            tasks = [task for task in (worker, watcher) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=max(0, end - loop.time()))
                for task in done:
                    if not task.cancelled():
                        task.exception()
                if pending:
                    # Python cannot force-kill callbacks that suppress cancellation.
                    result.execution['cleanup_status'] = 'unresponsive'
                    result.execution['status'] = 'error'
                    return
            adapter = state['adapter']
            try:
                if adapter is not None and self.owns_adapter:
                    close = getattr(adapter, 'aclose', None)
                    if not _async_callable(close):
                        raise ValueError('async_close_required')
                    closing = asyncio.create_task(close())
                    # Reserve part of the same finite allowance for cancellation finalizers.
                    done, pending = await asyncio.wait({closing}, timeout=max(0, end - loop.time()) * .8)
                    if pending:
                        closing.cancel()
                        drained, still_pending = await asyncio.wait({closing}, timeout=max(0, end - loop.time()))
                        for task in drained:
                            if not task.cancelled():
                                task.exception()
                        result.execution['cleanup_status'] = 'unresponsive' if still_pending else 'timeout'
                        result.execution['status'] = 'error'
                    else:
                        if closing.cancelled():
                            raise ValueError('cleanup_cancelled')
                        closing.result()
                        result.execution['cleanup_status'] = 'closed'
                elif adapter is not None:
                    result.execution['cleanup_status'] = 'borrowed'
            except Exception:
                result.execution['cleanup_status'] = 'error'
                result.execution['status'] = 'error'
            finally:
                if state['acquired'] and result.execution['cleanup_status'] != 'unresponsive':
                    self._semaphore.release()
                    state['acquired'] = False