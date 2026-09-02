from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class SetupSpec:
    user_id: str = "test-user"
    session_id: Optional[str] = None
    users: List[Dict[str, Any]] = field(default_factory=list)
    assets: List[Dict[str, Any]] = field(default_factory=list)
    knowledge: List[Dict[str, Any]] = field(default_factory=list)
    failures: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "session_id": self.session_id, "users": self.users, "assets": self.assets, "knowledge": self.knowledge, "failures": self.failures}


@dataclass(frozen=True)
class BusinessStateExpectation:
    path: str
    operator: str = "equals"
    value: Any = None

    def as_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "operator": self.operator, "value": self.value}


@dataclass(frozen=True)
class ResponseExpectation:
    contains: List[str] = field(default_factory=list)
    not_contains: List[str] = field(default_factory=list)
    sources_present: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"contains": self.contains, "not_contains": self.not_contains, "sources_present": self.sources_present}


@dataclass(frozen=True)
class ExpectedToolCall:
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    arguments_schema: Optional[Mapping[str, Any]] = None
    result_schema: Optional[Mapping[str, Any]] = None
    status: str = "succeeded"

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments, "arguments_schema": self.arguments_schema, "result_schema": self.result_schema, "status": self.status}


@dataclass(frozen=True)
class ExpectationSpec:
    tools: List[ExpectedToolCall] = field(default_factory=list)
    tool_order: List[str] = field(default_factory=list)
    strict_tool_order: bool = True
    business_state: List[BusinessStateExpectation] = field(default_factory=list)
    response: ResponseExpectation = field(default_factory=ResponseExpectation)

    def as_dict(self) -> Dict[str, Any]:
        return {"tools": [tool.as_dict() for tool in self.tools], "tool_order": self.tool_order, "strict_tool_order": self.strict_tool_order, "business_state": [item.as_dict() for item in self.business_state], "response": self.response.as_dict()}


@dataclass(frozen=True)
class ConversationStep:
    user: str
    expect: Optional[ExpectationSpec] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"user": self.user, "expect": self.expect.as_dict() if self.expect else None}


@dataclass(frozen=True)
class QualityExpectation:
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"metrics": self.metrics}


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    name: str
    conversation: List[ConversationStep]
    tags: List[str] = field(default_factory=list)
    setup: SetupSpec = field(default_factory=SetupSpec)
    expect: ExpectationSpec = field(default_factory=ExpectationSpec)
    quality: QualityExpectation = field(default_factory=QualityExpectation)
    source: str = "<memory>"

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "tags": self.tags, "setup": self.setup.as_dict(), "conversation": [step.as_dict() for step in self.conversation], "expect": self.expect.as_dict(), "quality": self.quality.as_dict(), "source": self.source}
