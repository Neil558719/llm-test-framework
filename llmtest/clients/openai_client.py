"""OpenAIClient —— OpenAI 兼容客户端。

通过 `base_url` 可切换到 DeepSeek / 通义千问 / Moonshot / vLLM 等任何
OpenAI 兼容接口。SDK 懒加载，Mock 模式不需要安装。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..specs import (
    ClaimVerdict,
    JudgeResult,
    JudgeSpec,
)
from ..evaluation import parse_semantic, parse_judge, parse_claims, parse_verdict
from .base import LLMClient
from . import prompts

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIClient(LLMClient):
    provider = "openai"
    name = "openai"

    def __init__(self, config):
        super().__init__(config)
        self._client: Any = None

    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "真实模式需要 openai SDK，请安装：pip install llmtest[real]"
                ) from exc
            kwargs: Dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: Optional[int],
    ) -> str:
        client = self._get_client()
        params: Dict[str, Any] = {
            "model": self.config.model or DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            params["max_tokens"] = max_tokens
        # 网关 5xx / 429 / 断连等瞬时错误自动重试
        resp = self._retry_call(lambda: client.chat.completions.create(**params))
        usage = getattr(resp, "usage", None)
        if usage is not None:
            from ..specs import TokenUsage
            self.last_usage = TokenUsage(int(getattr(usage, "prompt_tokens", 0)), int(getattr(usage, "completion_tokens", 0)))
        self.last_model_version = self.last_model_version.__class__(self.provider, params["model"])
        content = resp.choices[0].message.content
        return content or ""

    def _embed(self, text: str) -> List[float]:
        client = self._get_client()
        model = self.config.embedding_model or DEFAULT_EMBEDDING_MODEL
        resp = self._retry_call(lambda: client.embeddings.create(model=model, input=text))
        return list(resp.data[0].embedding)

    def _semantic_equivalent(
        self, actual: str, expected: str, context: Optional[str] = None
    ) -> Any:
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
