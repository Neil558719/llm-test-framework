"""Offline capability and policy regressions; no model/SDK call is permitted."""

import importlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from llmtest.assertions.similarity import EmbeddingUnavailableError, assert_similarity, similarity
from llmtest.clients.anthropic_client import AnthropicClient
from llmtest.clients.mock_client import MockLLMClient
from llmtest.clients.openai_client import OpenAIClient
from llmtest.config import Config
from llmtest.metrics.tracker import _Tracker
from llmtest.reporting.html_report import render_report

ROOT = Path(__file__).resolve().parents[1]


def forbidden(*args, **kwargs):
    pytest.fail('Real SDK/model/API call is forbidden in embedding policy tests')


def real_client(monkeypatch, policy=None):
    config = Config(mode='real') if policy is None else Config(mode='real', embedding_policy=policy)
    client = OpenAIClient(config)
    monkeypatch.setattr(client, '_get_client', forbidden)
    return client


def test_real_anthropic_without_provider_cannot_return_pseudo_vectors(monkeypatch):
    client = AnthropicClient(Config(mode='real', provider='anthropic'))
    monkeypatch.setattr(client, '_get_client', forbidden)
    with pytest.raises(EmbeddingUnavailableError):
        client.embed('actual')


def test_real_anthropic_without_provider_blocks_required_check(monkeypatch):
    client = AnthropicClient(Config(mode='real', provider='anthropic'))
    monkeypatch.setattr(client, '_get_client', forbidden)
    with pytest.raises(EmbeddingUnavailableError):
        assert_similarity('same', 'same', client=client)


def test_embedding_unavailable_error_has_a_public_stable_import():
    from llmtest import EmbeddingUnavailableError as public_error
    assert public_error is EmbeddingUnavailableError


def test_anthropic_can_use_an_explicit_real_embedding_client(monkeypatch):
    provider = real_client(monkeypatch)
    monkeypatch.setattr(provider, '_embed', lambda text: [1.0, 0.0])
    client = AnthropicClient(Config(mode='real', provider='anthropic'), embedding_client=provider)
    monkeypatch.setattr(client, '_get_client', forbidden)
    assert assert_similarity('different words', 'another sentence', client=client) == 1


def test_anthropic_cannot_label_mock_embeddings_as_real():
    with pytest.raises(ValueError):
        AnthropicClient(Config(mode='real', provider='anthropic'),
                        embedding_client=MockLLMClient(Config(mode='mock')))


def test_mock_similarity_is_explicitly_labelled_mock(monkeypatch):
    module = importlib.import_module('llmtest.assertions.similarity')
    tracker = _Tracker()
    rec = tracker.begin('mock', 'mock')
    monkeypatch.setattr(module, 'tracker', tracker)
    score = similarity('same', 'same', client=MockLLMClient(Config(mock_latency_ms=0)))
    assert score == 1
    metric = next(m for m in rec.metrics if m.name == 'similarity_score')
    assert metric.meta == 'mock'


def test_mock_embedding_provenance_is_visible_in_html(monkeypatch):
    module = importlib.import_module('llmtest.assertions.similarity')
    tracker = _Tracker()
    rec = tracker.begin('similarity', 'similarity')
    monkeypatch.setattr(module, 'tracker', tracker)
    similarity('same', 'same', client=MockLLMClient(Config(mock_latency_ms=0)))
    rendered = render_report(tracker.summarize(), [rec])
    assert 'similarity_score · mock' in rendered


def test_real_unavailable_check_never_records_a_pseudo_similarity_score(monkeypatch):
    module = importlib.import_module('llmtest.assertions.similarity')
    tracker = _Tracker()
    rec = tracker.begin('unavailable', 'unavailable')
    monkeypatch.setattr(module, 'tracker', tracker)
    client = AnthropicClient(Config(mode='real', provider='anthropic'))
    monkeypatch.setattr(client, '_get_client', forbidden)
    with pytest.raises(EmbeddingUnavailableError):
        assert_similarity('same', 'same', client=client)
    assert all(m.name != 'similarity_score' for m in rec.metrics)
    assert next(m for m in rec.metrics if m.name == 'embedding_coverage').value == 0


class StatusFailure(RuntimeError):
    def __init__(self, status_code):
        super().__init__('Controlled provider status failure')
        self.status_code = status_code


ERRORS = [TimeoutError('timeout'), ConnectionError('connection'), OSError('transport'),
          ValueError('configuration'), RuntimeError('unknown'),
          *[StatusFailure(status) for status in [400, 401, 403, 404, 429, 500, 501, 503]]]


@pytest.mark.parametrize('error', ERRORS, ids=['timeout', 'connection', 'transport', 'config', 'unknown',
                                             '400', '401', '403', '404', '429', '500', '501', '503'])
def test_failed_probe_does_not_cache_false_and_recovery_can_be_probed(monkeypatch, error):
    client = real_client(monkeypatch)
    def fail(text):
        raise error
    monkeypatch.setattr(client, '_embed', fail)
    with pytest.raises(type(error)) as caught:
        client.embedding_available()
    assert caught.value is error
    monkeypatch.setattr(client, '_embed', lambda text: [1.0, 0.0])
    assert client.embedding_available() is True


@pytest.mark.parametrize('error', [EmbeddingUnavailableError('unsupported'), NotImplementedError('unsupported')])
def test_only_definite_unsupported_is_cached(monkeypatch, error):
    client = real_client(monkeypatch)
    def fail(text):
        raise error
    monkeypatch.setattr(client, '_embed', fail)
    assert client.embedding_available() is False
    monkeypatch.setattr(client, '_embed', forbidden)
    assert client.embedding_available() is False


def test_failure_after_success_is_not_skipped_and_actual_call_can_recover(monkeypatch):
    client = real_client(monkeypatch, 'optional')
    monkeypatch.setattr(client, '_embed', lambda text: [1.0, 0.0])
    assert client.embedding_available() is True
    def timeout(text):
        raise TimeoutError('request failed after a successful capability probe')
    monkeypatch.setattr(client, '_embed', timeout)
    with pytest.raises(TimeoutError):
        assert_similarity('actual', 'expected', client=client)
    monkeypatch.setattr(client, '_embed', lambda text: [1.0, 0.0])
    assert assert_similarity('actual', 'expected', client=client) == 1


def test_explicit_embedding_client_probe_can_recover_from_timeout(monkeypatch):
    provider = real_client(monkeypatch)
    def timeout(text):
        raise TimeoutError('embedding provider timeout')
    monkeypatch.setattr(provider, '_embed', timeout)
    client = AnthropicClient(Config(mode='real', provider='anthropic'), embedding_client=provider)
    monkeypatch.setattr(client, '_get_client', forbidden)
    with pytest.raises(TimeoutError):
        client.embedding_available()
    monkeypatch.setattr(provider, '_embed', lambda text: [1.0, 0.0])
    assert client.embedding_available() is True


@pytest.mark.parametrize('error', ERRORS, ids=['timeout', 'connection', 'transport', 'config', 'unknown',
                                             '400', '401', '403', '404', '429', '500', '501', '503'])
def test_optional_policy_never_skips_operational_or_config_errors(monkeypatch, error):
    client = real_client(monkeypatch, 'optional')
    def fail(text):
        raise error
    monkeypatch.setattr(client, '_embed', fail)
    with pytest.raises(BaseException) as caught:
        assert_similarity('actual', 'expected', client=client)
    assert caught.value is error


def test_default_required_unavailable_is_not_a_pytest_skip(monkeypatch):
    client = real_client(monkeypatch)
    monkeypatch.setattr(client, '_embed', lambda text: (_ for _ in ()).throw(EmbeddingUnavailableError('unsupported')))
    with pytest.raises(BaseException) as caught:
        assert_similarity('actual', 'expected', client=client)
    assert isinstance(caught.value, EmbeddingUnavailableError)


def test_optional_skip_records_coverage_gap_without_similarity_score(monkeypatch):
    module = importlib.import_module('llmtest.assertions.similarity')
    tracker = _Tracker()
    rec = tracker.begin('optional', 'optional')
    monkeypatch.setattr(module, 'tracker', tracker)
    client = real_client(monkeypatch, 'optional')
    monkeypatch.setattr(client, '_embed', lambda text: (_ for _ in ()).throw(EmbeddingUnavailableError('unsupported')))
    with pytest.raises(pytest.skip.Exception, match='optional'):
        assert_similarity('actual', 'expected', client=client)
    coverage = next(m for m in rec.metrics if m.name == 'embedding_coverage')
    assert coverage.value == 0
    assert 'optional' in coverage.meta
    assert all(m.name != 'similarity_score' for m in rec.metrics)


def test_required_check_overrides_optional_exploration(monkeypatch):
    client = real_client(monkeypatch, 'optional')
    monkeypatch.setattr(client, '_embed', lambda text: (_ for _ in ()).throw(EmbeddingUnavailableError('unsupported')))
    with pytest.raises(EmbeddingUnavailableError):
        assert_similarity('actual', 'expected', client=client, required=True)


def test_false_required_flag_cannot_lower_default_required_policy(monkeypatch):
    client = real_client(monkeypatch)
    monkeypatch.setattr(client, '_embed', lambda text: (_ for _ in ()).throw(EmbeddingUnavailableError('unsupported')))
    with pytest.raises(EmbeddingUnavailableError):
        assert_similarity('actual', 'expected', client=client, required=False)


def test_measurement_never_skips_even_with_optional_policy(monkeypatch):
    client = real_client(monkeypatch, 'optional')
    monkeypatch.setattr(client, '_embed', lambda text: (_ for _ in ()).throw(EmbeddingUnavailableError('unsupported')))
    with pytest.raises(EmbeddingUnavailableError):
        similarity('actual', 'expected', client=client)


def test_embedding_policy_defaults_required_and_option_overrides_environment(monkeypatch):
    assert Config().embedding_policy == 'required'
    monkeypatch.setenv('LLM_EMBEDDING_POLICY', 'optional')
    assert Config.from_env().embedding_policy == 'optional'
    assert Config.from_pytest_options(SimpleNamespace(embedding_policy='required')).embedding_policy == 'required'


@pytest.mark.parametrize('policy', ['', 'auto', None])
def test_invalid_policy_is_a_configuration_error(policy):
    with pytest.raises(ValueError):
        Config(embedding_policy=policy)


@pytest.mark.parametrize('policy,required,exit_code,marker', [
    (None, False, 1, 'EmbeddingUnavailableError'),
    ('optional', False, 0, '1 skipped'),
    ('optional', True, 1, 'EmbeddingUnavailableError'),
])
def test_pytest_exit_codes_enforce_required_and_show_optional_coverage(tmp_path, policy, required, exit_code, marker):
    test = tmp_path / 'test_consumer_embedding.py'
    test.write_text('''from llmtest import assert_similarity
from llmtest.clients.anthropic_client import AnthropicClient

def test_required_embedding(llm_config, monkeypatch):
    client = AnthropicClient(llm_config)
    def forbidden(*args, **kwargs):
        raise AssertionError('Real SDK forbidden')
    monkeypatch.setattr(client, '_get_client', forbidden)
    assert_similarity('same', 'same', client=client''' + (', required=True' if required else '') + ')\n', encoding='utf-8')
    environment = os.environ.copy()
    environment['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    environment['PYTHONPATH'] = str(ROOT)
    environment['PYTHONIOENCODING'] = 'utf-8'
    report = tmp_path / 'report.html'
    command = [sys.executable, '-m', 'pytest', '-p', 'llmtest.plugin', '-c', str(ROOT / 'pyproject.toml'),
               '--llm-mode=real', '--llm-provider=anthropic', '--report', str(report), '--no-history', '-q', str(test)]
    if policy is not None:
        command += ['--embedding-policy', policy]
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', timeout=30)
    assert result.returncode == exit_code, result.stdout
    assert marker in result.stdout, result.stdout
    if policy == 'optional' and not required:
        rendered = report.read_text(encoding='utf-8')
        assert 'embedding_coverage' in rendered
        assert 'optional' in rendered