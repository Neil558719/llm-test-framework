from __future__ import annotations

import os
from dataclasses import dataclass

from llmtest import Config
from qe_platform.production.secrets import SecretSource


@dataclass(frozen=True)
class AgentModelConfig:
    profile: str = "mock"
    mode: str = "mock"
    provider: str = "mock"
    model: str = ""
    base_url: str = ""
    api_key: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None

    def __repr__(self) -> str:
        return (f"AgentModelConfig(profile={self.profile!r}, mode={self.mode!r}, "
                f"provider={self.provider!r}, model={self.model!r}, "
                f"base_url={self.base_url!r}, api_key='***', "
                f"temperature={self.temperature!r}, max_tokens={self.max_tokens!r})")

    ENV_NAMES = (
        "REFERENCE_AGENT_MODEL_MODE", "REFERENCE_AGENT_MODEL_PROVIDER",
        "REFERENCE_AGENT_MODEL", "REFERENCE_AGENT_MODEL_BASE_URL",
        "REFERENCE_AGENT_MODEL_API_KEY", "REFERENCE_AGENT_MODEL_TEMPERATURE",
        "REFERENCE_AGENT_MODEL_MAX_TOKENS",
    )

    @classmethod
    def from_env(cls) -> "AgentModelConfig":
        secrets = SecretSource.from_environment(os.environ)
        mode = os.getenv("REFERENCE_AGENT_MODEL_MODE", "mock").lower()
        provider = os.getenv("REFERENCE_AGENT_MODEL_PROVIDER", "").lower()
        if mode not in {"mock", "real"}:
            raise ValueError("REFERENCE_AGENT_MODEL_MODE must be mock or real")
        profile = "deepseek-official" if mode == "real" and provider == "deepseek" else ("mock" if mode == "mock" else "")
        base = os.getenv("REFERENCE_AGENT_MODEL_BASE_URL", "")
        if provider == "deepseek" and not base:
            base = "https://api.deepseek.com"
        return cls(profile=profile or "mock", mode=mode, provider=provider or "mock",
                   model=os.getenv("REFERENCE_AGENT_MODEL", ""), base_url=base,
                   api_key=secrets.get("REFERENCE_AGENT_MODEL_API_KEY"),
                   temperature=float(os.getenv("REFERENCE_AGENT_MODEL_TEMPERATURE", "0")),
                   max_tokens=int(os.environ["REFERENCE_AGENT_MODEL_MAX_TOKENS"]) if os.getenv("REFERENCE_AGENT_MODEL_MAX_TOKENS") else None)

    def to_llmtest_config(self) -> Config:
        return Config(mode=self.mode, provider=self.provider, model=self.model or None,
                      base_url=self.base_url or None, api_key=self.api_key)

    def as_public_dict(self) -> dict[str, object]:
        configured = self.mode == "mock" or bool(self.model and self.api_key)
        return {"profile": self.profile, "mode": self.mode, "provider": self.provider,
                "model": self.model, "base_url": self.base_url, "configured": configured}
