from __future__ import annotations

from dataclasses import dataclass, field
import math
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
    required: bool = True
    threshold: Optional[float] = None
    reason: str = ""
    provider: str = ""
    model: str = ""
    version: str = ""

    @property
    def evaluated(self) -> bool:
        return (self.status in ("passed", "failed") and self.required is True
                and type(self.score) in (int, float) and 0 <= self.score <= 1 and math.isfinite(self.score))

    def as_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "expectation": self.expectation,
                "status": self.status, "score": self.score, "message": self.message,
                "required": self.required, "threshold": self.threshold, "reason": self.reason,
                "provider": self.provider, "model": self.model, "version": self.version,
                "score_kind": "hallucination_rate" if self.metric == "hallucination" else "judge_rubric"}


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
    latency_ms: Optional[float] = None
    execution: Optional[dict[str, Any]] = None

    @property
    def total_usage(self):
        from llmtest import TokenUsage
        values = [step.response.usage for step in self.steps if step.response and step.response.usage]
        return TokenUsage(sum(v.prompt_tokens for v in values), sum(v.completion_tokens for v in values)) if values else None

    @property
    def total_cost(self):
        values = [step.response.cost for step in self.steps if step.response and step.response.cost]
        if not values:
            return None
        from llmtest import CostMetrics
        currencies = {v.currency for v in values}
        versions = {v.price_version for v in values}
        return CostMetrics(sum(v.input for v in values), sum(v.output for v in values), sum(v.total for v in values), currencies.pop() if len(currencies) == 1 else "MIXED", versions.pop() if len(versions) == 1 else "MIXED")

    @property
    def passed(self) -> bool:
        return (self.complete and bool(self.steps) and all(step.status == "passed" for step in self.steps)
                and all(item.passed for item in self.final_assertions)
                and all(item.evaluated and item.status == "passed" for item in self.quality_checks))

    @property
    def complete(self) -> bool:
        from .execution import execution_complete as async_execution_complete
        execution_complete = (
            len(self.steps) == self.expected_step_count
            and all(step.status != "error" for step in self.steps)
        )
        return (execution_complete and all(item.evaluated for item in self.quality_checks)
                and async_execution_complete(self.execution))

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "scenario_name": self.scenario_name,
            **({'execution': self.execution} if self.execution is not None else {}),
            "source": self.source, "session_id": self.session_id,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "passed": self.passed, "complete": self.complete,
            "latency_ms": self.latency_ms,
            "steps": [step.as_dict() for step in self.steps],
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "final_assertions": [item.as_dict() for item in self.final_assertions],
            "quality_checks": [item.as_dict() for item in self.quality_checks],
            "usage": self.total_usage.as_dict() if self.total_usage else None,
            "cost": self.total_cost.as_dict() if self.total_cost else None,
            "model_versions": [step.response.model_version.as_dict() for step in self.steps if step.response and step.response.model_version],
        }
