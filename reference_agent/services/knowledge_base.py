"""企业 IT 知识库 Mock 检索服务。"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .common import FailureConfig, MockServiceBase


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower()))


class KnowledgeBase(MockServiceBase):
    def __init__(
        self,
        records: list[dict[str, Any]] | None = None,
        failure: FailureConfig | None = None,
    ) -> None:
        super().__init__(failure)
        self._records = deepcopy(records or [])

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        self._before_call()
        query_tokens = _tokens(query)
        if not query_tokens or limit <= 0:
            return []

        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index, record in enumerate(self._records):
            text = f"{record.get('title', '')} {record.get('content', '')}"
            score = len(query_tokens & _tokens(text)) / len(query_tokens)
            if score > 0:
                ranked.append((score, index, record))
        ranked.sort(key=lambda item: (-item[0], item[1]))

        results = []
        for score, _, record in ranked[:limit]:
            result = deepcopy(record)
            result["score"] = score
            results.append(result)
        return results
