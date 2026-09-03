from __future__ import annotations

import pytest

from llmtest import Config
from reference_agent.runtime import AgentModelConfig, ModelProfile, ModelProviderRegistry


def test_agent_model_config_defaults_to_offline_mock(monkeypatch):
    for name in AgentModelConfig.ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    config = AgentModelConfig.from_env()

    assert config.profile == "mock"
    assert config.mode == "mock"
    assert config.as_public_dict() == {
        "profile": "mock",
        "mode": "mock",
        "provider": "mock",
        "model": "",
        "base_url": "",
        "configured": True,
    }


def test_deepseek_profile_maps_server_environment_without_exposing_secret(monkeypatch):
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_MODE", "real")
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("REFERENCE_AGENT_MODEL", "deepseek-chat")
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_API_KEY", "super-secret")

    config = AgentModelConfig.from_env()

    assert config.profile == "deepseek-official"
    assert config.to_llmtest_config() == Config(
        mode="real",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="super-secret",
    )
    assert "super-secret" not in repr(config)
    assert "api_key" not in config.as_public_dict()


def test_registry_is_extensible_without_changing_runtime():
    registry = ModelProviderRegistry.with_defaults()
    registry.register(
        ModelProfile("synthetic", "Synthetic", "real", "openai", "https://models.test/v1"),
        lambda config: object(),
    )

    profile = registry.resolve("synthetic")

    assert profile.provider == "openai"
    assert registry.create_client(AgentModelConfig(profile="synthetic", mode="real", provider="openai")) is not None


def test_registry_rejects_unknown_profile():
    registry = ModelProviderRegistry.with_defaults()

    with pytest.raises(ValueError, match="unknown model profile"):
        registry.resolve("anthropic")


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_MODE", "staging")
    with pytest.raises(ValueError, match="must be mock or real"):
        AgentModelConfig.from_env()
