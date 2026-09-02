from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from llmtest import ResponseEnvelope, ToolCall
from qe_platform.contracts import AssertionResult


@dataclass
class StepResult:
    index: int
    user: str
    status: str
    response: Optional[ResponseEnvelope] = None
    assertions: List[AssertionResult] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "user": self.user, "status": self.status,
            "response": self.response.as_dict() if self.response else None,
            "assertions": [item.as_dict() for item in self.assertions],
            "error": self.error,
        }


@dataclass
class QualityCheckResult:
    metric: str
    expectation: Any
    status: str = "not_executed"
    score: Optional[float] = None
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "expectation": self.expectation,
                "status": self.status, "score": self.score, "message": self.message}


@dataclass
class ScenarioRunResult:
    scenario_id: str
    scenario_name: str
    source: str
    session_id: str
    started_at: str
    finished_at: str = ""
    expected_step_count: int = 0
    steps: List[StepResult] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    final_assertions: List[AssertionResult] = field(default_factory=list)
    quality_checks: List[QualityCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(step.status == "passed" for step in self.steps) and all(item.passed for item in self.final_assertions)

    @property
    def complete(self) -> bool:
        execution_complete = (
            len(self.steps) == self.expected_step_count
            and all(step.status != "error" for step in self.steps)
        )
        return execution_complete and all(item.status != "not_executed" for item in self.quality_checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "scenario_name": self.scenario_name,
            "source": self.source, "session_id": self.session_id,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "passed": self.passed, "complete": self.complete,
            "steps": [step.as_dict() for step in self.steps],
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "final_assertions": [item.as_dict() for item in self.final_assertions],
            "quality_checks": [item.as_dict() for item in self.quality_checks],
        }
