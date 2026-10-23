"""相似度断言：基于文本向量余弦相似度。

默认 required：缺能力抛 EmbeddingUnavailableError。只有显式 optional 探索
允许明确不支持时 skip；required=True 的单项检查始终必需。
"""

from __future__ import annotations

from typing import Optional

import pytest

from ..metrics.tracker import tracker
from ..clients.base import EmbeddingUnavailableError
from ..registry import get_default_client
from ..utils import cosine_similarity


def similarity(
    actual: str,
    expected: str,
    *,
    client=None,
) -> float:
    """测量两段文本的向量余弦相似度（0~1），并记录指标。

    Embedding 不可用时抛 EmbeddingUnavailableError。
    """
    client = client or get_default_client()
    if not client.embedding_available():
        raise EmbeddingUnavailableError(
            "评测客户端没有可用的 Embedding 模型（网关可能未开通 embedding），向量相似度无法计算"
        )
    score = cosine_similarity(client.embed(actual), client.embed(expected))
    tracker.record_metric("similarity_score", score, meta=client.embedding_source)
    tracker.record_metric("embedding_coverage", 1.0, meta=client.embedding_source)
    return score


def assert_similarity(
    actual: str,
    expected: str,
    *,
    client=None,
    threshold: float = 0.7,
    required: Optional[bool] = None,
) -> float:
    """断言相似度 ≥ threshold。失败抛 AssertionError。

    required=None 遵循客户端 embedding_policy；True 强制必需；False 不降低
    全局 required。未来 manifest 的必需项应传 required=True，optional 不能覆盖。
    仅明确不支持时 optional 探索可 skip，并记录覆盖缺失；网络/认证等错误直接抛出。
    """
    client = client or get_default_client()
    if required is not None and type(required) is not bool:
        raise ValueError("required must be a boolean or None")
    must_evaluate = required is True or client.config.embedding_policy == "required"
    try:
        score = similarity(actual, expected, client=client)
    except EmbeddingUnavailableError as exc:
        policy = "required" if must_evaluate else "optional"
        tracker.record_metric("embedding_coverage", 0.0, meta=f"{policy}: unsupported embedding")
        if must_evaluate:
            raise
        pytest.skip(f"optional embedding coverage missing: {exc}")
    passed = score >= threshold
    message = (
        f"相似度断言失败: 余弦相似度 {score:.3f} < 阈值 {threshold:.3f}\n"
        f"实际回答: {actual[:200]}\n期望文本: {expected[:200]}"
    )
    tracker.add_assertion("assert_similarity", passed, message, score, threshold)
    if not passed:
        raise AssertionError(message)
    return score
