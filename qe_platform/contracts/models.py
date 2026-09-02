"""契约校验使用的公共数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ToolContract:
    """声明一个工具的名称、参数 Schema 和可选结果 Schema。"""

    name: str
    arguments_schema: Mapping[str, Any]
    result_schema: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class AssertionResult:
    """一次确定性校验的结构化结果。"""

    assertion_type: str
    passed: bool
    message: str
    path: str = ""
    expected: Any = None
    actual: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "assertion_type": self.assertion_type,
            "passed": self.passed,
            "message": self.message,
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
        }
