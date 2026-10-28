"""Measured latency, protocol success and streaming evidence semantics."""
import asyncio
import json
from types import SimpleNamespace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from llmtest import ResponseEnvelope
from qe_platform.loadtest.metrics import summarize
from qe_platform.loadtest.models import LoadTestConfig, SampleResult
from qe_platform.loadtest.models import LoadTestRun
from qe_platform.loadtest.runner import LoadTestRunner
from qe_platform.loadtest.gate_models import GateThresholds
from qe_platform.loadtest.gates import evaluate_thresholds
from qe_platform.quality_loop.engine import build_trends
from qe_platform.scenarios import load_scenario_text
from qe_platform.workflow_runner import ScenarioRunner, ScenarioRunResult
from reference_agent.app import create_app
from tests.test_reference_agent_telemetry import RecordingTelemetrySink
from tests.test_workflow_runner import SequenceAdapter


def envelope(**changes):
    return {**ResponseEnvelope(answer='ok', sources=['context'], trace_id='trace', conversation_id='session').as_dict(), **changes}


class Stream:
    def __init__(self, events, content_type='text/event-stream', status=200):
        self.events, self.status_code = events, status
        self.headers = {'content-type': content_type}

    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False

    async def aiter_lines(self):
        for event in self.events:
            if isinstance(event, Exception): raise event
            yield event if isinstance(event, str) else 'data: ' + json.dumps(event)


class Client:
    def __init__(self, payload=None, events=None, content_type='text/event-stream', status=200, failure=None):
        self.payload, self.events = payload, events
        self.content_type, self.status, self.failure = content_type, status, failure

    async def post(self, *args, **kwargs):
        return httpx.Response(self.status, content=json.dumps(self.payload), headers={'content-type': 'application/json'})

    def stream(self, *args, **kwargs):
        if self.failure: raise self.failure
        return Stream(self.events, self.content_type, self.status)


def sample(client, protocol='http'):
    return asyncio.run(LoadTestRunner(LoadTestConfig('http://local', protocol=protocol))._sample(client))


@pytest.mark.parametrize('payload', [{}, [], {'answer': 'ok'}, envelope(answer=1), envelope(sources='bad'), envelope(tool_calls={}), envelope(trace_id=None)])
def test_http_requires_valid_response_contract(payload):
    value = sample(Client(payload=payload))
    assert value.success is False
    assert value.error_type == 'invalid_response' and value.status_code == 200


def test_protocol_success_is_separate_from_business_success():
    value = sample(Client(payload=envelope(metadata={'ticket_status': 'unavailable'})))
    assert value.success and value.observations['ticket_status'] == 'unavailable'


def test_complete_only_cannot_manufacture_ttft():
    value = sample(Client(events=[{'type': 'complete', 'response': envelope()}]), 'sse')
    assert value.success and value.ttft_ms is None
    assert value.content_first_event_ms is None


def test_simulated_chunks_are_content_not_model_ttft():
    value = sample(Client(events=[{'type': 'start', 'stream_mode': 'simulated'}, {'type': 'chunk', 'text': ''},
                                 {'type': 'chunk', 'text': 'ok'}, {'type': 'complete', 'response': envelope(metadata={'stream_mode': 'simulated'})}]), 'sse')
    assert value.ttft_ms is None
    assert value.content_first_event_ms is not None and value.stream_mode == 'simulated'


@pytest.mark.parametrize('payload', [{}, envelope(answer=[]), None])
def test_sse_complete_requires_valid_response_contract(payload):
    value = sample(Client(events=[{'type': 'complete', 'response': payload}]), 'sse')
    assert not value.success and value.error_type == 'invalid_response'
    assert value.status_code == 200 and value.stream_established


def test_connection_failure_is_not_an_established_stream_interruption():
    value = sample(Client(failure=httpx.ConnectTimeout('offline fixture')), 'sse')
    assert value.error_type == 'timeout' and not value.stream_interrupted
    assert not value.stream_established and value.status_code is None


@pytest.mark.parametrize('failure', [httpx.ReadTimeout('offline'), 'data: {bad json'])
def test_established_stream_failure_preserves_status_and_content(failure):
    value = sample(Client(events=[{'type': 'chunk', 'text': 'content'}, failure]), 'sse')
    assert value.status_code == 200
    assert value.stream_interrupted and value.stream_established
    assert value.content_first_event_ms is not None


def test_non_sse_content_type_is_not_an_established_stream():
    value = sample(Client(events=[{'type': 'complete', 'response': envelope()}], content_type='application/json'), 'sse')
    assert not value.success and value.error_type == 'invalid_response'
    assert not value.stream_established


def test_errors_do_not_increase_goodput():
    values = [SampleResult(False, 1, None, status_code=500, error_type='http_error') for _ in range(100)]
    summary = summarize(values, LoadTestConfig('http://local', requests=100), wall_time_ms=100)
    assert summary.goodput_rps == 0
    assert summary.throughput_rps == 1000 and summary.error_rate == 1
    assert all(value is None for value in summary.success_latency_ms.values())


def test_success_latency_uses_only_success_samples_and_same_wall_time():
    summary = summarize([SampleResult(True, 100, None), SampleResult(False, 1, None)],
                        LoadTestConfig('http://local', requests=2), wall_time_ms=1000)
    assert summary.goodput_rps == 1 and summary.throughput_rps == 2
    assert summary.success_latency_ms['p95'] == 100 and summary.latency_ms['p95'] != 100


def test_stream_rate_denominator_is_established_streams():
    values = [sample(Client(events=[], status=429), 'sse'),
              sample(Client(failure=httpx.ConnectTimeout('offline')), 'sse'),
              sample(Client(failure=httpx.ConnectTimeout('offline again')), 'sse'),
              sample(Client(events=[httpx.ReadTimeout('offline')]), 'sse'),
              sample(Client(events=[{'type': 'complete', 'response': envelope()}]), 'sse')]
    summary = summarize(values, LoadTestConfig('http://local', protocol='sse', requests=5), wall_time_ms=1000)
    assert summary.stream_interruption_rate == .5
    assert summary.stream_established_count == 2 and summary.rate_429 == .2


def test_no_established_streams_is_unavailable_not_zero_interruptions():
    summary = summarize([sample(Client(events=[], status=429), 'sse')],
                        LoadTestConfig('http://local', protocol='sse'), wall_time_ms=100)
    assert summary.stream_interruption_rate is None


def test_response_and_trace_share_measured_latency_before_emit(monkeypatch):
    sink = RecordingTelemetrySink()
    app = create_app(':memory:', telemetry_sink=sink)
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr('reference_agent.app.perf_counter', lambda: next(ticks), raising=False)
    body = TestClient(app).post('/api/chat', json={'message': 'hello'}).json()
    assert body['latency']['total_ms'] == 125
    assert sink.events[0].as_dict()['latency']['total_ms'] == 125
    assert body['latency']['ttft_ms'] is None


def test_reference_stream_is_explicitly_simulated():
    app = create_app(':memory:')
    response = TestClient(app).post('/api/chat/stream', json={'message': 'hello'})
    events = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
    assert events[0]['stream_mode'] == 'simulated'
    assert events[-1]['response']['metadata']['stream_mode'] == 'simulated'
    assert events[-1]['response']['latency']['ttft_ms'] is None


def test_scenario_latency_is_monotonic(monkeypatch):
    spec = load_scenario_text('id: x\nname: X\nconversation: [{user: hello}]')[0]
    ticks = iter([5.0, 5.25])
    monkeypatch.setattr('qe_platform.workflow_runner.runner.perf_counter', lambda: next(ticks), raising=False)
    result = ScenarioRunner(lambda _: SequenceAdapter([ResponseEnvelope(answer='ok')])).run(spec)
    assert result.as_dict()['latency_ms'] == 250


def test_unmeasured_scenario_latency_remains_null():
    result = ScenarioRunResult('x', 'X', '', 'session', '2026-10-28T00:00:00Z')
    assert result.as_dict()['latency_ms'] is None


def test_goodput_threshold_cannot_be_met_by_fast_errors():
    summary = summarize([SampleResult(False, 1, None, status_code=500)], LoadTestConfig('http://local'), wall_time_ms=1)
    checks = evaluate_thresholds(summary, GateThresholds(min_goodput_rps=1), 'recovery')
    assert not checks[0].passed and checks[0].actual == 0


@pytest.mark.parametrize('field', ['min_goodput_rps', 'max_content_first_event_p95_ms'])
@pytest.mark.parametrize('value', [True, '1', -1, float('nan'), float('inf')])
def test_new_thresholds_reject_invalid_values(field, value):
    with pytest.raises(ValueError):
        GateThresholds(**{field: value})


def test_missing_content_metric_fails_configured_gate():
    summary = summarize([SampleResult(True, 10, None)], LoadTestConfig('http://local'), wall_time_ms=10)
    checks = evaluate_thresholds(summary, GateThresholds(max_content_first_event_p95_ms=20), 'recovery')
    assert not checks[0].passed and checks[0].actual is None


def test_null_online_latency_stays_unmeasured_in_trends():
    class Repository:
        def online_rows(self, **kwargs):
            return [dict(trace_id='x', application='app', version='v', timestamp='2026-10-28T00:00:00Z',
                         feedback_count=0, confirmed_low_quality_count=0, latency_ms=None, total_tokens=0, total_cost=0)]
        def list_runs(self, **kwargs): return []
    assert build_trends(Repository())[0].p95_latency_ms is None


def test_load_report_explains_attempt_goodput_content_and_null_stream_rate(tmp_path):
    from qe_platform.loadtest.reporting import write_reports
    config = LoadTestConfig('http://local', json_report=str(tmp_path / 'run.json'), html_report=str(tmp_path / 'run.html'))
    values = [SampleResult(True, 100, None)]
    run = LoadTestRun(config, 'start', 'finish', values, summarize(values, config, wall_time_ms=1000))
    json_path, html_path = write_reports(run)
    payload, text = json.loads(json_path.read_text(encoding='utf-8')), html_path.read_text(encoding='utf-8')
    assert payload['summary']['goodput_rps'] == 1
    for label in ('completed_attempts', 'goodput_rps', 'content_first_event_ms', 'stream_established_count', 'not model TTFT'):
        assert label in text
    assert 'unavailable' in text


def test_gate_report_includes_new_metric_definitions(tmp_path):
    from tests.test_loadtest_gate_reporting import gate_result
    from qe_platform.loadtest.gate_reporting import write_gate_reports
    _, html_path = write_gate_reports(gate_result(tmp_path))
    text = html_path.read_text(encoding='utf-8')
    for label in ('goodput_rps', 'content_first_event_ms', 'success_latency_ms', 'stream_established_count', 'completed_attempts', 'not model TTFT'):
        assert label in text


def test_measured_scenario_report_import_preserves_a06_trust(monkeypatch, tmp_path):
    from qe_platform.reporting import build_run_report, write_html
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.quality_loop.models import parse_run_report
    spec = load_scenario_text('id: timed\nname: Timed\nconversation: [{user: hi}]')[0]
    ticks = iter([5.0, 5.25])
    monkeypatch.setattr('qe_platform.workflow_runner.runner.perf_counter', lambda: next(ticks))
    result = ScenarioRunner(lambda _: SequenceAdapter([ResponseEnvelope(answer='ok')])).run(spec)
    plan = freeze_run_manifest([spec])
    report = build_run_report([result], application='app', release_id='release', version='v', manifest=plan)
    payload = report.as_dict()
    imported = parse_run_report(payload, 'offline', expected_manifest=plan)
    assert imported.p95_latency_ms == 250 and imported.verification == 'verified_v2'
    assert parse_run_report(payload, 'untrusted').verification != 'verified_v2'
    html = write_html(report, tmp_path / 'scenario.html').read_text(encoding='utf-8')
    assert 'Dialogue latency ms' in html and '250.0' in html


def test_server_latency_correlates_to_online_trend(monkeypatch, tmp_path):
    from qe_platform.storage import SQLiteTelemetryRepository
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    database = str(tmp_path / 'traces.db')
    repository = SQLiteTelemetryRepository(database, hash_key='test-key')
    sink = RecordingTelemetrySink()
    sink.emit = repository.upsert_trace
    app = create_app(':memory:', telemetry_sink=sink)
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr('reference_agent.app.perf_counter', lambda: next(ticks))
    body = TestClient(app).post('/api/chat', json={'message': 'hello'}).json()
    quality = SQLiteQualityRepository(database)
    assert quality.online_rows()[0]['trace_id'] == body['trace_id']
    assert build_trends(quality)[0].p95_latency_ms == body['latency']['total_ms'] == 125


def test_null_online_latency_is_not_replaced_with_zero(tmp_path):
    from qe_platform.storage import SQLiteTelemetryRepository
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    from tests.test_telemetry_storage import trace_at, utc
    from dataclasses import replace
    database = str(tmp_path / 'traces.db')
    repository = SQLiteTelemetryRepository(database, hash_key='test-key', clock=lambda: utc('2026-09-01T00:00:00+00:00'))
    repository.upsert_trace(replace(trace_at('2026-08-29T00:00:00+00:00'), latency={'status': 'succeeded'}))
    quality = SQLiteQualityRepository(database, clock=lambda: utc('2026-09-01T00:00:00+00:00'))
    assert quality.online_rows()[0]['latency_ms'] is None
    assert build_trends(quality)[0].p95_latency_ms is None


@pytest.mark.parametrize('field,value', [('cost', {'total': 10 ** 400}), ('usage', {'prompt_tokens': True}),
                                       ('cost', {'total': float('nan')}), ('cost', {'total': -1})])
def test_malformed_optional_observability_is_controlled_invalid_response(field, value):
    result = sample(Client(payload=envelope(**{field: value})))
    assert not result.success and result.error_type == 'invalid_response' and result.status_code == 200


def test_first_content_clock_ignores_start_comments_empty_and_complete(monkeypatch):
    ticks = iter([0.0, .04, .1])
    monkeypatch.setattr('qe_platform.loadtest.runner.time', SimpleNamespace(perf_counter=lambda: next(ticks)))
    value = sample(Client(events=[': heartbeat', {'type': 'start'}, {'type': 'chunk', 'text': ''},
                                 {'type': 'chunk', 'text': 'ok'}, {'type': 'complete', 'response': envelope()}]), 'sse')
    assert value.content_first_event_ms == 40 and value.duration_ms == 100
    assert value.ttft_ms == 40 and value.ttft_source == 'client_first_content'


def test_simulated_mode_learned_at_completion_clears_legacy_ttft():
    value = sample(Client(events=[{'type': 'chunk', 'text': 'ok'},
                                 {'type': 'complete', 'response': envelope(metadata={'stream_mode': 'simulated'})}]), 'sse')
    assert value.content_first_event_ms is not None and value.ttft_ms is None
    assert value.stream_mode == 'simulated' and value.ttft_source == 'unavailable'


def test_new_gate_config_loads_and_enforces_same_boundaries(tmp_path):
    from qe_platform.loadtest.gate_config import load_gate_config
    path = tmp_path / 'gate.yaml'
    path.write_text('id: a07\ntarget_url: http://local\nfault_token_env: TEST_TOKEN\nthresholds: {min_goodput_rps: 1, max_content_first_event_p95_ms: 1000}\nscenarios:\n  - id: fault\n    fault: {type: model_timeout}\n    expect: {status_code: 200}\n', encoding='utf-8')
    thresholds = load_gate_config(path).thresholds
    values = [SampleResult(True, 10, 1000, content_first_event_ms=1000)]
    summary = summarize(values, LoadTestConfig('http://local'), wall_time_ms=1000)
    assert all(check.passed for check in evaluate_thresholds(summary, thresholds, 'recovery'))


def test_warmup_does_not_enter_sample_or_wall_denominator(monkeypatch):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr('qe_platform.loadtest.runner.time', SimpleNamespace(perf_counter=lambda: clock.value))
    class WarmClient(Client):
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            clock.value += 1
            return httpx.Response(200, json=envelope())
    config = LoadTestConfig('http://local', requests=2, warmup_requests=3)
    run = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: WarmClient()).run())
    assert clock.value == 5 and len(run.samples) == 2
    assert run.summary.wall_time_ms == 2000 and run.summary.goodput_rps == run.summary.throughput_rps == 1


def test_judge_time_is_outside_scenario_latency(monkeypatch):
    from qe_platform.workflow_runner import QualityCheckResult
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr('qe_platform.workflow_runner.runner.perf_counter', lambda: clock.value)
    spec = load_scenario_text('id: x\nname: X\nconversation: [{user: hello}]\nquality: {relevance: {min_score: 0.8}}')[0]
    class Adapter:
        def send(self, *args, **kwargs):
            clock.value += 1
            return ResponseEnvelope(answer='ok')
    def judge(scenario, response):
        clock.value += 100
        return [QualityCheckResult('relevance', {'min_score': .8}, 'passed', 1)]
    result = ScenarioRunner(lambda _: Adapter(), quality_evaluator=judge).run(spec)
    assert clock.value == 101 and result.latency_ms == 1000 and result.passed


def test_zero_stream_denominator_blocks_configured_interruption_gate():
    values = [sample(Client(events=[], status=429), 'sse')]
    summary = summarize(values, LoadTestConfig('http://local', protocol='sse'), wall_time_ms=1000)
    checks = evaluate_thresholds(summary, GateThresholds(max_stream_interruption_rate=0), 'recovery')
    assert not checks[0].passed and checks[0].actual is None


def test_legacy_summary_does_not_invent_goodput_evidence():
    from tests.test_loadtest_gates import _summary
    check = evaluate_thresholds(_summary(), GateThresholds(min_goodput_rps=0), 'recovery')[0]
    assert not check.passed and check.actual is None


def test_packaged_gate_applies_stream_limits_only_to_sse():
    from qe_platform.loadtest.gate_config import load_gate_config
    path = Path(__file__).resolve().parents[1] / 'configs' / 'm13-reference-agent-gate.yaml'
    suite = load_gate_config(path)
    for scenario in suite.scenarios:
        if scenario.load.protocol == 'sse':
            assert scenario.thresholds.max_stream_interruption_rate == 0
            assert scenario.thresholds.max_content_first_event_p95_ms == 1000
        else:
            assert scenario.thresholds.max_stream_interruption_rate is None


def test_packaged_m13_gate_runs_all_seven_local_fault_recoveries(tmp_path):
    from qe_platform.loadtest.gate_config import load_gate_config
    from qe_platform.loadtest.gate_runner import GateSuiteRunner
    from reference_agent.faults import FaultControlSettings
    from reference_agent.services import UserService, AssetService, KnowledgeBase
    from llmtest.cost import PriceTable
    path = Path(__file__).resolve().parents[1] / 'configs' / 'm13-reference-agent-gate.yaml'
    suite = load_gate_config(path)
    app = create_app(str(tmp_path / 'agent.db'), fault_settings=FaultControlSettings(True, 'local-token'),
                     price_table=PriceTable.from_mapping({'mock/': {'input_per_1k': 0, 'output_per_1k': 0, 'version': 'offline-fixture'}}),
                     knowledge_base=KnowledgeBase([{'document_id': 'email', 'title': '邮箱密码', 'content': '公司邮箱密码在自助服务重置。'}]),
                     user_service=UserService({'U1001': {'user_id': 'U1001', 'name': 'Test'}}),
                     asset_service=AssetService({'PC-1001': {'asset_id': 'PC-1001', 'owner_id': 'U1001', 'status': 'active'}}))
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kwargs)
    result = asyncio.run(GateSuiteRunner(suite, client_factory=factory, environ={suite.fault_token_env: 'local-token'}).run())
    assert len(result.scenarios) == 7
    assert result.gate_passed, [(s.scenario_id, c.name, c.reason) for s in result.scenarios for c in s.checks if not c.passed]