"""Native asynchronous case-budget contracts; no real provider calls."""
import importlib
import asyncio
import json

import httpx
import pytest
from llmtest import ResponseEnvelope
from qe_platform.scenarios import load_scenario_text


def api():
    from qe_platform.workflow_runner import AsyncScenarioRunner, ExecutionBudget
    return AsyncScenarioRunner, ExecutionBudget


def spec(quality=''):
    return load_scenario_text('id: async-case\nname: Async\nconversation: [{user: hi}]\n' + quality)[0]


class Adapter:
    retry_safe = False
    def __init__(self): self.closed, self.calls = False, 0
    async def send(self, *args, **kwargs):
        self.calls += 1
        return ResponseEnvelope(answer='ok')
    async def aclose(self): self.closed = True


def test_execution_budget_interface_exists():
    assert getattr(importlib.import_module('qe_platform.workflow_runner.budget'), 'ExecutionBudget')


def test_async_runner_interface_exists():
    assert getattr(importlib.import_module('qe_platform.workflow_runner.async_runner'), 'AsyncScenarioRunner')


def test_async_dify_interface_exists():
    assert getattr(importlib.import_module('qe_platform.adapters.dify'), 'AsyncDifyAdapter')


@pytest.mark.parametrize('field,value', [('case_timeout_s', True), ('case_timeout_s', 0), ('case_timeout_s', -1),
    ('case_timeout_s', float('nan')), ('case_timeout_s', float('inf')), ('case_timeout_s', '1'),
    ('max_attempts', True), ('max_attempts', 0), ('max_attempts', 1.5), ('max_attempts', '2'),
    ('retry_backoff_s', -1), ('retry_backoff_s', True), ('cleanup_timeout_s', 0)])
def test_budget_rejects_invalid_controls(field, value):
    _, Budget = api()
    with pytest.raises(ValueError): Budget(**{field: value})


@pytest.mark.parametrize('value', [True, 0, -1, 1.5])
def test_concurrency_rejects_invalid_controls(value):
    Runner, _ = api()
    with pytest.raises(ValueError): Runner(lambda _: Adapter(), max_concurrency=value)


@pytest.mark.asyncio
async def test_hanging_adapter_reaches_case_deadline_and_closes():
    Runner, Budget = api()
    class Hanging(Adapter):
        async def send(self, *args, **kwargs):
            self.calls += 1
            await asyncio.Event().wait()
    adapter = Hanging()
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=.025))
    assert not result.complete and not result.passed and adapter.closed
    assert result.steps[0].status == 'error' and result.steps[0].response is None
    assert 'deadline' in result.steps[0].error
    assert result.execution['status'] == 'deadline' and result.execution['effect_unknown']
    assert result.execution['stage_ms']['request'] > 0


@pytest.mark.asyncio
async def test_queue_wait_is_inside_deadline_without_releasing_unowned_permit():
    Runner, Budget = api()
    started, release = asyncio.Event(), asyncio.Event()
    class Held(Adapter):
        async def send(self, *args, **kwargs):
            started.set()
            await release.wait()
            return ResponseEnvelope(answer='ok')
    created = []
    def factory(_):
        value = Held(); created.append(value); return value
    runner = Runner(factory, max_concurrency=1)
    first = asyncio.create_task(runner.run(spec(), budget=Budget(case_timeout_s=1)))
    await started.wait()
    queued = await runner.run(spec(), budget=Budget(case_timeout_s=.02))
    assert not queued.complete and len(created) == 1 and queued.latency_ms is None
    assert queued.execution['stage_ms']['queue'] > 0 and not queued.execution['effect_unknown']
    third = asyncio.create_task(runner.run(spec(), budget=Budget(case_timeout_s=1)))
    await asyncio.sleep(.01)
    assert len(created) == 1
    release.set()
    assert (await first).passed and (await third).passed
    assert all(value.closed for value in created)


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['init', 'rate_wait'])
async def test_initialization_and_limiter_are_inside_total_deadline(stage):
    Runner, Budget = api()
    async def hanging(*args): await asyncio.Event().wait()
    runner = Runner(hanging if stage == 'init' else lambda _: Adapter(), limiter=hanging if stage == 'rate_wait' else None)
    result = await runner.run(spec(), budget=Budget(case_timeout_s=.02))
    assert not result.complete and not result.execution['effect_unknown']
    assert result.latency_ms is None and result.execution['stage_ms'][stage] > 0


@pytest.mark.asyncio
async def test_single_deadline_is_not_reset_after_initialization():
    Runner, Budget = api()
    class Delayed(Adapter):
        async def send(self, *args, **kwargs):
            await asyncio.sleep(.16)
            return ResponseEnvelope(answer='ok')
    async def factory(_):
        await asyncio.sleep(.08)
        return Delayed()
    result = await Runner(factory).run(spec(), budget=Budget(case_timeout_s=.2))
    assert result.execution['status'] == 'deadline' and not result.complete
    assert result.execution['stage_ms']['init'] > 0 and result.execution['stage_ms']['request'] > 0


@pytest.mark.asyncio
async def test_cancel_event_and_external_task_cancellation_close_owned_adapter():
    Runner, Budget = api()
    entered = asyncio.Event()
    class Held(Adapter):
        async def send(self, *args, **kwargs): entered.set(); await asyncio.Event().wait()
    adapter, cancel = Held(), asyncio.Event()
    run = asyncio.create_task(Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, cancel_event=cancel)))
    await entered.wait(); cancel.set()
    result = await run
    assert result.execution['status'] == 'cancelled' and adapter.closed and not result.complete
    entered.clear(); other = Held()
    task = asyncio.create_task(Runner(lambda _: other).run(spec(), budget=Budget(case_timeout_s=1)))
    await entered.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert other.closed


@pytest.mark.asyncio
async def test_pre_cancelled_case_does_not_initialize_or_submit():
    Runner, Budget = api()
    cancel = asyncio.Event(); cancel.set()
    adapter = Adapter()
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, cancel_event=cancel))
    assert result.execution['status'] == 'cancelled' and not adapter.closed and adapter.calls == 0
    assert not result.execution['effect_unknown'] and result.latency_ms is None


@pytest.mark.asyncio
async def test_borrowed_adapter_is_not_closed():
    Runner, Budget = api()
    adapter = Adapter()
    result = await Runner(lambda _: adapter, owns_adapter=False).run(spec(), budget=Budget(case_timeout_s=1))
    assert result.passed and not adapter.closed and result.execution['cleanup_status'] == 'borrowed'


@pytest.mark.asyncio
async def test_hanging_close_is_bounded_and_not_a_successful_case():
    Runner, Budget = api()
    class BadClose(Adapter):
        async def aclose(self): await asyncio.Event().wait()
    result = await Runner(lambda _: BadClose()).run(spec(), budget=Budget(case_timeout_s=1, cleanup_timeout_s=.02))
    assert result.execution['cleanup_status'] == 'timeout' and not result.passed and not result.complete
    assert len(result.steps) == 1 and result.steps[0].response is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('retry_safe,retryable,attempts,expected', [(False, True, 3, 1), (True, False, 3, 1), (True, True, 1, 1), (True, True, 2, 2)])
async def test_retry_requires_explicit_idempotency_and_retryable_failure(retry_safe, retryable, attempts, expected):
    Runner, Budget = api()
    from qe_platform.adapters import AsyncApplicationAdapterError
    class Flaky(Adapter):
        async def send(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise AsyncApplicationAdapterError('controlled', retryable=retryable)
            return ResponseEnvelope(answer='ok')
    adapter = Flaky(); adapter.retry_safe = retry_safe
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, max_attempts=attempts))
    assert adapter.calls == expected and result.passed == (expected == 2)
    assert len(result.execution['attempts']) == expected
    assert len({entry['operation_key'] for entry in result.execution['attempts']}) == 1


@pytest.mark.asyncio
async def test_effect_unknown_forbids_retry_even_when_adapter_claims_idempotency():
    Runner, Budget = api()
    from qe_platform.adapters import AsyncApplicationAdapterError
    class Unknown(Adapter):
        retry_safe = True
        async def send(self, *args, **kwargs):
            self.calls += 1
            raise AsyncApplicationAdapterError('unknown', retryable=True, effect_unknown=True)
    adapter = Unknown()
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, max_attempts=3))
    assert adapter.calls == 1 and result.execution['effect_unknown'] and not result.complete


@pytest.mark.asyncio
async def test_backoff_consumes_same_deadline():
    Runner, Budget = api()
    from qe_platform.adapters import AsyncApplicationAdapterError
    class Retry(Adapter):
        retry_safe = True
        async def send(self, *args, **kwargs):
            self.calls += 1
            raise AsyncApplicationAdapterError('retry', retryable=True)
    adapter = Retry()
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=.02, max_attempts=3, retry_backoff_s=.1))
    assert adapter.calls == 1 and result.execution['status'] == 'deadline'
    assert result.execution['stage_ms']['backoff'] > 0 and not result.execution['effect_unknown']


@pytest.mark.asyncio
async def test_required_async_evaluation_timeout_preserves_real_steps_and_imports():
    Runner, Budget = api()
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.quality_loop.models import parse_run_report
    async def evaluate(*args): await asyncio.Event().wait()
    scenario = spec('quality: {relevance: {min_score: 0.8}}\n')
    budget = Budget(case_timeout_s=.02)
    result = await Runner(lambda _: Adapter(), quality_evaluator=evaluate).run(scenario, budget=budget)
    assert len(result.steps) == 1 and result.steps[0].status == 'passed'
    assert result.steps[0].response is not None and not result.complete
    assert result.latency_ms is not None and result.execution['stage_ms']['evaluation'] > 0
    assert result.quality_checks[0].status == 'not_executed'
    plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': result.execution['policy']})
    report = build_run_report([result], manifest=plan, application='app', release_id='release', version='v')
    imported = parse_run_report(report.as_dict(), 'offline', expected_manifest=plan)
    assert not imported.complete and not imported.release_eligible


@pytest.mark.asyncio
async def test_sync_quality_callback_is_explicitly_unsupported_and_not_called():
    Runner, Budget = api()
    called = []
    def evaluate(*args): called.append(True); return []
    result = await Runner(lambda _: Adapter(), quality_evaluator=evaluate).run(spec('quality: {relevance: {min_score: 0.8}}\n'), budget=Budget(case_timeout_s=1))
    assert not result.complete and not called
    assert result.quality_checks[0].reason == 'async_evaluator_required'


@pytest.mark.asyncio
async def test_async_quality_callback_validates_required_policy_and_grounding():
    Runner, Budget = api()
    from qe_platform.workflow_runner import QualityCheckResult
    async def evaluate(scenario, response):
        return [QualityCheckResult('relevance', {'min_score': .8}, 'passed', .9, provider='mock', model='fixture')]
    scenario = spec('quality: {relevance: {min_score: 0.8}, faithfulness: {min_score: 0.8}}\n')
    result = await Runner(lambda _: Adapter(), quality_evaluator=evaluate).run(scenario, budget=Budget(case_timeout_s=1))
    assert not result.passed and not result.complete
    assert {check.metric: check.status for check in result.quality_checks} == {'relevance': 'passed', 'faithfulness': 'inconclusive'}


@pytest.mark.asyncio
async def test_async_dify_yields_and_preserves_user_session_mapping_and_borrowed_client():
    from qe_platform.adapters import AsyncDifyAdapter, DifyAdapterConfig
    payloads = []
    async def handle(request):
        await asyncio.sleep(0)
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'answer': 'ok', 'conversation_id': 'remote-' + payloads[-1]['user']})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = AsyncDifyAdapter(DifyAdapterConfig('http://offline.test', 'fixture'), client=client)
        await adapter.send('one', user_id='u', session_id='s')
        await adapter.send('two', user_id='u', session_id='s')
        await adapter.send('three', user_id='other', session_id='s')
        await adapter.aclose()
        assert not client.is_closed
    assert 'conversation_id' not in payloads[0] and payloads[1]['conversation_id'] == 'remote-u'
    assert 'conversation_id' not in payloads[2]


@pytest.mark.asyncio
async def test_v1_async_reference_factory_report_and_policy_identity(tmp_path):
    from qe_platform.v1_gate import run_gate_async
    _, Budget = api()
    from qe_platform.quality_loop.models import parse_run_report
    from qe_platform import scenarios as scenario_package
    from pathlib import Path
    json_path, html_path = tmp_path / 'run.json', tmp_path / 'run.html'
    code = await run_gate_async(asset_dir=Path(scenario_package.__file__).parent / 'assets' / 'reference_agent', json_path=json_path,
                               html_path=html_path, budget=Budget(case_timeout_s=3), max_concurrency=2,
                               application='app', release_id='release', version='v')
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert code == 0 and payload['passed'] == payload['total'] == 14
    assert all(row['execution']['status'] == 'completed' for row in payload['scenarios'])
    assert 'execution_policy' in payload['manifest']['scoring_assets']
    assert parse_run_report(payload, 'untrusted').verification != 'verified_v2'
    assert 'execution' in html_path.read_text(encoding='utf-8').lower()


@pytest.mark.parametrize('field', ['case_timeout_s', 'retry_backoff_s', 'cleanup_timeout_s'])
def test_oversized_budget_integer_is_controlled_value_error(field):
    _, Budget = api()
    with pytest.raises(ValueError): Budget(**{field: 10 ** 400})


@pytest.mark.asyncio
async def test_cleanup_timeout_drains_cooperative_close_finalizer():
    Runner, Budget = api()
    class SlowClose(Adapter):
        async def aclose(self):
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.001)
                self.closed = True
    adapter = SlowClose()
    before = set(asyncio.all_tasks())
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, cleanup_timeout_s=.5))
    assert result.execution['cleanup_status'] == 'timeout'
    assert adapter.closed and set(asyncio.all_tasks()) <= before


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['execution', 'attempt'])
async def test_execution_evidence_rejects_unknown_fields_before_safe_persistence(location):
    Runner, Budget = api()
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest
    scenario = spec()
    result = await Runner(lambda _: Adapter()).run(scenario, budget=Budget(case_timeout_s=1))
    target = result.execution if location == 'execution' else result.execution['attempts'][0]
    target['private_blob'] = 'untrusted arbitrary content'
    plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': result.execution['policy']})
    with pytest.raises(ValueError): build_run_report([result], manifest=plan)


@pytest.mark.asyncio
async def test_request_returning_after_cancellation_cannot_rewrite_interrupted_evidence():
    Runner, Budget = api()
    class Late(Adapter):
        async def send(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return ResponseEnvelope(answer='late')
    result = await Runner(lambda _: Late()).run(spec(), budget=Budget(case_timeout_s=.02))
    assert result.execution['status'] == 'deadline'
    assert len(result.steps) == 1 and result.steps[0].status == 'error' and result.steps[0].response is None
    assert result.execution['attempts'][0]['status'] == 'deadline' and not result.complete


@pytest.mark.asyncio
async def test_factory_returning_after_deadline_cannot_dispatch_request():
    Runner, Budget = api()
    adapter = Adapter()
    async def factory(_):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return adapter
    result = await Runner(factory).run(spec(), budget=Budget(case_timeout_s=.02))
    assert adapter.calls == 0 and adapter.closed
    assert result.execution['status'] == 'deadline' and not result.complete


@pytest.mark.asyncio
async def test_bounded_many_cases_leave_no_worker_or_monitor_tasks():
    Runner, Budget = api()
    active, peak = 0, 0
    class Concurrent(Adapter):
        async def send(self, *args, **kwargs):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            try:
                await asyncio.sleep(.005)
                return ResponseEnvelope(answer='ok')
            finally:
                active -= 1
    before = set(asyncio.all_tasks())
    results = await Runner(lambda _: Concurrent(), max_concurrency=2).run_many([spec() for _ in range(5)], budget=Budget(case_timeout_s=1))
    assert all(value.passed for value in results) and peak == 2 and active == 0
    assert set(asyncio.all_tasks()) <= before


@pytest.mark.asyncio
async def test_second_external_cancellation_does_not_orphan_cleanup():
    Runner, Budget = api()
    entered, closing = asyncio.Event(), asyncio.Event()
    class Held(Adapter):
        async def send(self, *args, **kwargs): entered.set(); await asyncio.Event().wait()
        async def aclose(self):
            closing.set()
            await asyncio.sleep(.02)
            self.closed = True
    adapter = Held()
    before = set(asyncio.all_tasks())
    task = asyncio.create_task(Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1)))
    await entered.wait(); task.cancel()
    await closing.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert adapter.closed and set(asyncio.all_tasks()) <= before


@pytest.mark.asyncio
async def test_bad_response_and_assertion_failures_are_never_retried():
    Runner, Budget = api()
    class Invalid(Adapter):
        retry_safe = True
        async def send(self, *args, **kwargs): self.calls += 1; return {}
    adapter = Invalid()
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=1, max_attempts=3))
    assert adapter.calls == 1 and not result.complete
    scenario = load_scenario_text('id: x\nname: X\nconversation: [{user: hi, expect: {response: {contains: [missing]}}}]')[0]
    valid = Adapter(); valid.retry_safe = True
    result = await Runner(lambda _: valid).run(scenario, budget=Budget(case_timeout_s=1, max_attempts=3))
    assert valid.calls == 1 and result.complete and not result.passed


@pytest.mark.asyncio
async def test_policy_change_requires_new_baseline_and_persistence_retains_execution(tmp_path):
    Runner, Budget = api()
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    from qe_platform.quality_loop.engine import validate_release
    from qe_platform.quality_loop.models import ReleaseGatePolicy
    scenario = spec()
    repository = SQLiteQualityRepository(tmp_path / 'quality.db')
    fingerprints = []
    for number in (1, 2):
        result = await Runner(lambda _: Adapter()).run(scenario, budget=Budget(case_timeout_s=number))
        plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': result.execution['policy']})
        payload = build_run_report([result], run_id='run' + str(number), manifest=plan,
            application='app', release_id='release', version='v').as_dict()
        run = repository.import_run(payload, source_label='offline', expected_manifest=plan)
        loaded = repository.get_run(run.run_id)
        assert loaded.release_eligible and loaded.evidence['scenarios'][0]['execution'] == result.execution
        fingerprints.append(loaded.asset_fingerprint)
    assert fingerprints[0] != fingerprints[1]
    with pytest.raises(ValueError, match='controlled assets differ'):
        validate_release(repository, 'run1', 'run2', ReleaseGatePolicy())
    repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['init', 'second_request', 'cleanup'])
async def test_incomplete_execution_roundtrips_verified_report_without_release(stage, tmp_path):
    Runner, Budget = api()
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    scenario = load_scenario_text('id: x\nname: X\nconversation: [{user: one}, {user: two}]')[0]
    class Partial(Adapter):
        async def send(self, *args, **kwargs):
            self.calls += 1
            if stage == 'second_request' and self.calls == 2: await asyncio.Event().wait()
            return ResponseEnvelope(answer='ok')
        async def aclose(self):
            if stage == 'cleanup': await asyncio.Event().wait()
            self.closed = True
    def factory(_):
        if stage == 'init': raise ValueError('private exception must not persist')
        return Partial()
    result = await Runner(factory).run(scenario, budget=Budget(case_timeout_s=.03, cleanup_timeout_s=.04))
    plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': result.execution['policy']})
    payload = build_run_report([result], manifest=plan, application='app', release_id='release', version='v').as_dict()
    assert 'private exception' not in json.dumps(payload)
    repository = SQLiteQualityRepository(tmp_path / 'incomplete.db')
    run = repository.import_run(payload, source_label='offline', expected_manifest=plan)
    loaded = repository.get_run(run.run_id)
    assert not loaded.complete and not loaded.release_eligible
    assert loaded.evidence['scenarios'][0]['execution']['status'] != 'completed'
    repository.close()


@pytest.mark.asyncio
async def test_native_dify_owned_client_closes_after_request_timeout(monkeypatch):
    Runner, Budget = api()
    from qe_platform.adapters import AsyncDifyAdapter, DifyAdapterConfig
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def handle(request):
        entered.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client)
    adapter = AsyncDifyAdapter(DifyAdapterConfig('http://offline.test', 'fixture'))
    result = await Runner(lambda _: adapter).run(spec(), budget=Budget(case_timeout_s=.03))
    assert entered.is_set() and cancelled.is_set() and client.is_closed
    assert result.execution['effect_unknown'] and not result.complete


@pytest.mark.asyncio
async def test_native_dify_serializes_same_user_session_updates():
    from qe_platform.adapters import AsyncDifyAdapter, DifyAdapterConfig
    payloads = []
    async def handle(request):
        payloads.append(json.loads(request.content))
        await asyncio.sleep(.005)
        return httpx.Response(200, json={'answer': 'ok', 'conversation_id': 'remote'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = AsyncDifyAdapter(DifyAdapterConfig('http://offline.test', 'fixture'), client=client)
        await asyncio.gather(adapter.send('one', user_id='u', session_id='s'), adapter.send('two', user_id='u', session_id='s'))
    assert 'conversation_id' not in payloads[0] and payloads[1]['conversation_id'] == 'remote'


@pytest.mark.asyncio
async def test_v1_dify_factory_uses_native_adapter_and_v2_report(tmp_path, monkeypatch):
    _, Budget = api()
    import qe_platform.adapters as adapters
    from qe_platform.v1_gate import run_gate_async
    real_adapter = adapters.AsyncDifyAdapter
    async def handle(request): return httpx.Response(200, json={'answer': 'ok', 'conversation_id': 'remote'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(adapters, 'AsyncDifyAdapter', lambda config: real_adapter(config, client=client))
        assets = tmp_path / 'assets'; assets.mkdir()
        (assets / 'one.yaml').write_text('id: x\nname: X\nconversation: [{user: hi}]', encoding='utf-8')
        code = await run_gate_async(asset_dir=assets, json_path=tmp_path / 'run.json', html_path=tmp_path / 'run.html',
            adapter='dify', dify_config=adapters.DifyAdapterConfig('http://offline.test', 'fixture'), budget=Budget(case_timeout_s=1))
        assert not client.is_closed
    payload = json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))
    assert code == 0 and payload['verification'] == 'verified_v2' and payload['total'] == 1


def test_v1_sync_cli_does_not_silently_accept_async_budget_options():
    from qe_platform.v1_gate import main
    with pytest.raises(SystemExit) as error: main(['--case-timeout', '1'])
    assert error.value.code == 2


def test_runner_can_be_constructed_before_event_loop():
    Runner, Budget = api()
    runner = Runner(lambda _: Adapter(), max_concurrency=1)
    results = asyncio.run(runner.run_many([spec(), spec()], budget=Budget(case_timeout_s=1)))
    assert all(result.passed for result in results)


@pytest.mark.asyncio
async def test_async_evaluation_is_measured_separately_from_dialogue_latency():
    Runner, Budget = api()
    from qe_platform.workflow_runner import QualityCheckResult
    async def evaluate(scenario, response):
        await asyncio.sleep(.03)
        return [QualityCheckResult('relevance', {'min_score': .8}, 'passed', 1, provider='mock', model='fixture')]
    result = await Runner(lambda _: Adapter(), quality_evaluator=evaluate).run(spec('quality: {relevance: {min_score: 0.8}}\n'), budget=Budget(case_timeout_s=1))
    assert result.passed and result.latency_ms < result.execution['stage_ms']['evaluation']


@pytest.mark.asyncio
async def test_inline_factory_expiring_budget_cannot_dispatch_after_return():
    import time
    Runner, Budget = api()
    adapter = Adapter()
    def factory(_):
        time.sleep(.025)
        return adapter
    result = await Runner(factory).run(spec(), budget=Budget(case_timeout_s=.01))
    assert adapter.calls == 0 and adapter.closed
    assert result.execution['status'] == 'deadline' and not result.complete


@pytest.mark.asyncio
async def test_native_reference_factory_owns_and_closes_local_resources():
    import sqlite3
    from qe_platform.adapters import AsyncReferenceAgentAdapter
    adapter = AsyncReferenceAgentAdapter.from_setup(spec().setup)
    await adapter.aclose()
    assert adapter.client.is_closed
    with pytest.raises(sqlite3.ProgrammingError):
        adapter._local_app.state.store.get_session('closed')


@pytest.mark.asyncio
async def test_self_cancelled_close_is_cleanup_failure_not_external_case_cancellation():
    Runner, Budget = api()
    class SelfCancelled(Adapter):
        async def aclose(self): raise asyncio.CancelledError
    before = set(asyncio.all_tasks())
    result = await Runner(lambda _: SelfCancelled()).run(spec(), budget=Budget(case_timeout_s=1))
    assert result.execution['cleanup_status'] == 'error' and result.execution['status'] == 'error'
    assert not result.complete and set(asyncio.all_tasks()) <= before


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['deadline', 'cancel_event', 'unknown_exception', 'invalid_response'])
async def test_review_dispatched_retry_safe_request_still_has_unknown_effect(failure):
    Runner, Budget = api()
    entered, cancel = asyncio.Event(), asyncio.Event()
    class Idempotent(Adapter):
        retry_safe = True
        async def send(self, *args, **kwargs):
            self.calls += 1
            entered.set()
            if failure == 'unknown_exception':
                raise RuntimeError('outcome not established')
            if failure == 'invalid_response':
                return {}
            await asyncio.Event().wait()
    adapter = Idempotent()
    task = asyncio.create_task(Runner(lambda _: adapter).run(spec(), budget=Budget(
        case_timeout_s=.04 if failure == 'deadline' else 1, cancel_event=cancel, max_attempts=3)))
    await entered.wait()
    if failure == 'cancel_event':
        cancel.set()
    result = await task
    assert adapter.calls == 1 and adapter.closed and not result.complete
    assert result.execution['effect_unknown'] is True
    assert result.execution['attempts'][0]['effect_unknown'] is True


def _damage_review_attempts(execution, damage):
    if damage == 'no_attempts':
        execution['attempts'] = []
    elif damage == 'attempt_deadline':
        execution['attempts'][-1]['status'] = 'deadline'
    elif damage == 'unexpected_index':
        execution['attempts'][-1]['step_index'] = 99
    elif damage == 'missing_middle':
        del execution['attempts'][1]
    elif damage == 'reversed_steps':
        execution['attempts'].reverse()
    elif damage == 'retry_after_completed':
        duplicate = dict(execution['attempts'][-1], attempt=2)
        execution['attempts'].append(duplicate)


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['build', 'strict_parse', 'stored_reader'])
@pytest.mark.parametrize('damage', ['no_attempts', 'attempt_deadline', 'unexpected_index',
                                  'missing_middle', 'reversed_steps', 'retry_after_completed'])
async def test_review_attempts_must_match_controlled_step_coverage_and_outcome(boundary, damage):
    from copy import deepcopy
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest, digest
    from qe_platform.quality_loop.models import parse_run_report
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    Runner, Budget = api()
    scenario = load_scenario_text('id: coverage\nname: Coverage\nconversation: [{user: one}, {user: two}, {user: three}]')[0]
    budget = Budget(case_timeout_s=2, max_attempts=2)
    # The plan is selected before execution, independently of result coverage claims.
    plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': budget.policy(4)})
    result = await Runner(lambda _: Adapter()).run(scenario, budget=budget)
    payload = build_run_report([result], manifest=plan, application='app', release_id='release', version='v').as_dict()
    assert parse_run_report(payload, 'offline', expected_manifest=plan).release_eligible
    if boundary == 'build':
        _damage_review_attempts(result.execution, damage)
        with pytest.raises(ValueError):
            build_run_report([result], manifest=plan)
    elif boundary == 'strict_parse':
        _damage_review_attempts(payload['scenarios'][0]['execution'], damage)
        with pytest.raises(ValueError):
            parse_run_report(payload, 'offline', expected_manifest=plan)
    else:
        repository = SQLiteQualityRepository(':memory:')
        try:
            run = repository.import_run(payload, source_label='offline', expected_manifest=plan)
            stored = deepcopy(run.as_dict())
            _damage_review_attempts(stored['evidence']['scenarios'][0]['execution'], damage)
            proof = stored['evidence']
            # Recompute the ordinary content digest: this must hit semantic validation.
            proof['sha256'] = digest({key: value for key, value in proof.items() if key != 'sha256'})
            with repository._transaction():
                repository._connection.execute('UPDATE quality_offline_runs SET payload = ? WHERE run_id = ?',
                                               (json.dumps(stored), run.run_id))
            with pytest.raises(ValueError):
                repository.get_run(run.run_id)
        finally:
            repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['retry_success', 'init_interruption', 'evaluation_interruption'])
async def test_review_known_attempt_outcomes_keep_truthful_roundtrip(outcome):
    from qe_platform.adapters import AsyncApplicationAdapterError
    from qe_platform.reporting import build_run_report
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    Runner, Budget = api()
    class Known(Adapter):
        retry_safe = True
        async def send(self, *args, **kwargs):
            self.calls += 1
            if outcome == 'retry_success' and self.calls == 1:
                raise AsyncApplicationAdapterError('known failure', retryable=True, effect_unknown=False)
            return ResponseEnvelope(answer='ok')
    async def factory(_):
        if outcome == 'init_interruption':
            raise ValueError('initialization failed before dispatch')
        return Known()
    async def evaluate(*args):
        await asyncio.Event().wait()
    scenario = spec('quality: {relevance: {min_score: 0.8}}\n' if outcome == 'evaluation_interruption' else '')
    budget = Budget(case_timeout_s=.04 if outcome == 'evaluation_interruption' else 1, max_attempts=2)
    plan = freeze_run_manifest([scenario], scoring_assets={'execution_policy': budget.policy(4)})
    result = await Runner(factory, quality_evaluator=evaluate).run(scenario, budget=budget)
    assert result.execution['effect_unknown'] is False
    attempts = result.execution['attempts']
    expected = {'retry_success': ['error', 'completed'], 'init_interruption': [], 'evaluation_interruption': ['completed']}
    assert [attempt['status'] for attempt in attempts] == expected[outcome]
    assert all(attempt['effect_unknown'] is False for attempt in attempts)
    payload = build_run_report([result], manifest=plan, application='app', release_id='release', version='v').as_dict()
    repository = SQLiteQualityRepository(':memory:')
    try:
        run = repository.import_run(payload, source_label='offline', expected_manifest=plan)
        loaded = repository.get_run(run.run_id)
        assert loaded.release_eligible == (outcome == 'retry_success')
        assert loaded.evidence['scenarios'][0]['execution'] == result.execution
    finally:
        repository.close()