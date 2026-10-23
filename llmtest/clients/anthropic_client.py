"""AnthropicClient —— 调用 Claude 系列模型。

Anthropic 没有原生 Embedding 接口；需要显式注入真实 embedding_client。
未注入时报告能力不可用；语义/Judge/幻觉判定仍走 Anthropic LLM。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..specs import (
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
    SemanticResult,
)
from ..evaluation import parse_semantic, parse_judge, parse_claims, parse_verdict
from .base import LLMClient, EmbeddingUnavailableError
from . import prompts

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicClient(LLMClient):
    provider = "anthropic"
    name = "anthropic"

    def __init__(self, config, *, embedding_client: Optional[LLMClient] = None):
        super().__init__(config)
        if embedding_client is not None and (
            embedding_client.is_mock or embedding_client.provider == "mock"
        ):
            raise ValueError("A real Anthropic client requires a real embedding client, not Mock")
        self._client: Any = None
        self._embedding_client = embedding_client

    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "真实模式需要 anthropic SDK，请安装：pip install llmtest[real]"
                ) from exc
            kwargs: Dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = Anthropic(**kwargs)
        return self._client

    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        client = self._get_client()
        # anthropic API：system 提示单独传顶层参数
        system = None
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content")
            else:
                chat_messages.append(msg)
        params: Dict[str, Any] = {
            "model": self.config.model or DEFAULT_MODEL,
            "messages": chat_messages,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        # 网关 5xx / 429 / 断连等瞬时错误自动重试
        resp = self._retry_call(lambda: client.messages.create(**params))
        usage = getattr(resp, "usage", None)
        if usage is not None:
            from ..specs import TokenUsage
            self.last_usage = TokenUsage(int(getattr(usage, "input_tokens", 0)), int(getattr(usage, "output_tokens", 0)))
        self.last_model_version = self.last_model_version.__class__(self.provider, params["model"])
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts)

    def _embed(self, text: str) -> List[float]:
        if self._embedding_client is None:
            raise EmbeddingUnavailableError(
                "Anthropic has no native embedding API; configure an explicit real embedding client"
            )
        return self._embedding_client.embed(text)

    @property
    def embedding_source(self) -> str:
        return self._embedding_client.embedding_source if self._embedding_client is not None else self.provider

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> SemanticResult:
        raw = self._llm_json(prompts.semantic_prompt(actual, expected, context))
        return parse_semantic(raw)

    def _judge(
        self,
        response: str,
        spec: JudgeSpec,
        context: Optional[str] = None,
        question: Optional[str] = None,
    ) -> JudgeResult:
        raw = self._llm_json(
            prompts.judge_prompt(response, spec.criteria, spec.scale, context, question)
        )
        return parse_judge(raw, spec)

    def _extract_claims(self, text: str) -> List[str]:
        raw = self._llm_json(prompts.claim_extraction_prompt(text))
        return parse_claims(raw)

    def _verify_claim(self, claim: str, context: str) -> ClaimVerdict:
        raw = self._llm_json(prompts.claim_verify_prompt(claim, context))
        return parse_verdict(raw, claim)
