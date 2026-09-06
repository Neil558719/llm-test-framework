from __future__ import annotations

import json

import pytest

from reference_agent.faults import (
    FaultControlError,
    FaultControlSettings,
    InjectedDatabaseError,
    ModelRateLimitError,
)
from reference_agent.services import ServiceError


def test_fault_control_without_header_is_a_noop_when_disabled():
    assert FaultControlSettings(enabled=False, token="").resolve(None, None) is None


def test_fault_control_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REFERENCE_AGENT_TEST_FAULTS_ENABLED", raising=False)
    monkeypatch.delenv("REFERENCE_AGENT_TEST_FAULT_TOKEN", raising=False)

    settings = FaultControlSettings.from_env()

    assert settings == FaultControlSettings(enabled=False, token="")
    with pytest.raises(FaultControlError) as error:
        settings.resolve("secret", '{"type":"model_timeout"}')
    assert error.value.status_code == 403


@pytest.mark.parametrize("enabled", ["true", "1", "yes", "on", "TRUE"])
def test_enabled_fault_control_requires_non_empty_server_token(monkeypatch, enabled):
    monkeypatch.setenv("REFERENCE_AGENT_TEST_FAULTS_ENABLED", enabled)
    monkeypatch.setenv("REFERENCE_AGENT_TEST_FAULT_TOKEN", "  ")

    with pytest.raises(RuntimeError, match="TEST_FAULT_TOKEN"):
        FaultControlSettings.from_env()


def test_fault_control_rejects_missing_or_wrong_credentials():
    settings = FaultControlSettings(enabled=True, token="secret")

    for supplied in (None, "", "wrong"):
        with pytest.raises(FaultControlError) as error:
            settings.resolve(supplied, '{"type":"model_timeout"}')
        assert error.value.status_code == 403
        assert "credentials" in str(error.value)


@pytest.mark.parametrize(
    "raw,match",
    [
        ("{", "valid JSON"),
        ("[]", "JSON object"),
        ('{"type":"model_timeout","extra":1}', "unknown"),
        ('{"type":"not-supported"}', "unsupported"),
        ('{"type":1}', "type must be a string"),
    ],
)
def test_fault_control_rejects_malformed_or_unknown_profiles(raw, match):
    settings = FaultControlSettings(enabled=True, token="secret")

    with pytest.raises(FaultControlError) as error:
        settings.resolve("secret", raw)

    assert error.value.status_code == 400
    assert match in str(error.value)


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"type": "downstream_5xx"}, "target"),
        ({"type": "downstream_5xx", "target": "knowledge"}, "target"),
        ({"type": "downstream_5xx", "target": "ticket", "status_code": 499}, "status_code"),
        ({"type": "downstream_5xx", "target": "ticket", "status_code": 600}, "status_code"),
        ({"type": "tool_slow_response", "target": "asset"}, "delay_seconds"),
        ({"type": "tool_slow_response", "target": "asset", "delay_seconds": 0}, "delay_seconds"),
        ({"type": "tool_slow_response", "target": "asset", "delay_seconds": 5.1}, "delay_seconds"),
        ({"type": "tool_slow_response", "target": "database", "delay_seconds": 0.01}, "target"),
        ({"type": "model_timeout", "target": "ticket"}, "not allowed"),
        ({"type": "database_error", "status_code": 503}, "not allowed"),
    ],
)
def test_fault_profile_validates_type_specific_parameters(payload, match):
    settings = FaultControlSettings(enabled=True, token="secret")

    with pytest.raises(FaultControlError) as error:
        settings.resolve("secret", json.dumps(payload))

    assert error.value.status_code == 400
    assert match in str(error.value)


def test_fault_profile_parses_supported_parameters_and_uses_default_5xx_status():
    settings = FaultControlSettings(enabled=True, token="secret")

    downstream = settings.resolve(
        "secret", json.dumps({"type": "downstream_5xx", "target": "ticket"})
    )
    slow = settings.resolve(
        "secret",
        json.dumps({"type": "tool_slow_response", "target": "asset", "delay_seconds": 0.01}),
    )

    assert downstream is not None
    assert downstream.type == "downstream_5xx"
    assert downstream.target == "ticket"
    assert downstream.status_code == 503
    assert slow is not None
    assert slow.delay_seconds == 0.01


def test_fault_primitives_raise_only_at_the_matching_boundary():
    settings = FaultControlSettings(enabled=True, token="secret")
    database = settings.resolve("secret", '{"type":"database_error"}')
    timeout = settings.resolve("secret", '{"type":"model_timeout"}')
    rate_limit = settings.resolve("secret", '{"type":"model_429"}')
    downstream = settings.resolve(
        "secret", '{"type":"downstream_5xx","target":"ticket","status_code":500}'
    )

    assert database is not None and timeout is not None
    assert rate_limit is not None and downstream is not None
    with pytest.raises(InjectedDatabaseError):
        database.before_database()
    database.before_model()
    database.before_service("ticket")
    with pytest.raises(TimeoutError):
        timeout.before_model()
    with pytest.raises(ModelRateLimitError):
        rate_limit.before_model()
    downstream.before_service("asset")
    with pytest.raises(ServiceError) as error:
        downstream.before_service("ticket")
    assert error.value.status_code == 500
    assert error.value.message == "injected downstream_5xx for ticket"
