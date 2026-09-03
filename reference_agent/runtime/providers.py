from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from llmtest import get_client
from .config import AgentModelConfig


@dataclass(frozen=True)
class ModelProfile:
    name: str
    label: str
    mode: str
    provider: str
    base_url: str = ""


class ModelProviderRegistry:
    def __init__(self):
        self._profiles: dict[str, tuple[ModelProfile, Callable[[AgentModelConfig], Any]]] = {}

    @classmethod
    def with_defaults(cls):
        registry = cls()
        registry.register(ModelProfile("mock", "Mock", "mock", "mock"), lambda c: get_client(c.to_llmtest_config()))
        registry.register(ModelProfile("deepseek-official", "DeepSeek 官方", "real", "deepseek", "https://api.deepseek.com"), lambda c: get_client(c.to_llmtest_config()))
        return registry

    def register(self, profile: ModelProfile, factory: Callable[[AgentModelConfig], Any]):
        self._profiles[profile.name] = (profile, factory)

    def resolve(self, name: str) -> ModelProfile:
        try:
            return self._profiles[name][0]
        except KeyError as exc:
            raise ValueError(f"unknown model profile: {name}") from exc

    def profiles(self) -> list[ModelProfile]:
        return [item[0] for item in self._profiles.values()]

    def create_client(self, config: AgentModelConfig):
        try:
            return self._profiles[config.profile][1](config)
        except KeyError as exc:
            raise ValueError(f"unknown model profile: {config.profile}") from exc
