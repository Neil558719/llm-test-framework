from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import jsonschema
import yaml

from qe_platform.contracts import ToolContract
from .models import BusinessStateExpectation, ConversationStep, ExpectationSpec, ExpectedToolCall, QualityExpectation, ResponseExpectation, ScenarioSpec, SetupSpec
from .schema import SCENARIO_SCHEMA


class ScenarioLoadError(ValueError):
    def __init__(self, source: str, path: str, message: str):
        self.source, self.path, self.message = source, path, message
        super().__init__(f"{source}:{path}: {message}")


def _fail(source: str, path: str, message: str):
    raise ScenarioLoadError(source, path, message)


def _validate(data: Any, source: str) -> List[Dict[str, Any]]:
    if data is None:
        _fail(source, "$", "empty document")
    documents = data.get("scenarios") if isinstance(data, dict) and "scenarios" in data else [data]
    if not isinstance(documents, list) or not documents:
        _fail(source, "scenarios", "must be a non-empty list")
    result = []
    for index, item in enumerate(documents):
        try:
            jsonschema.Draft202012Validator(SCENARIO_SCHEMA).validate(item)
        except jsonschema.ValidationError as exc:
            parts = []
            for part in exc.absolute_path:
                parts.append(f"[{part}]" if isinstance(part, int) else (("." if parts else "") + str(part)))
            item_path = "".join(parts) or "$"
            path = f"scenarios[{index}].{item_path}" if len(documents) > 1 else item_path
            _fail(source, path, exc.message)
        result.append(item)
    return result


def _expect(raw: Dict[str, Any] | None, source: str, path: str) -> ExpectationSpec:
    raw = raw or {}
    tools = []
    for index, item in enumerate(raw.get("tools", [])):
        try:
            if item.get("arguments_schema") is not None or item.get("result_schema") is not None:
                ToolContract(item["name"], item.get("arguments_schema", {"type": "object"}), item.get("result_schema"))
        except (jsonschema.SchemaError, KeyError) as exc:
            _fail(source, f"{path}.tools[{index}].arguments_schema", str(exc))
        tools.append(ExpectedToolCall(item["name"], item.get("arguments", {}), item.get("arguments_schema"), item.get("result_schema"), item.get("status", "succeeded")))
    business = []
    for index, item in enumerate(raw.get("business_state", [])):
        if item.get("operator", "equals") not in {"equals", "exists", "contains", "not_equals"}:
            _fail(source, f"{path}.business_state[{index}].operator", "unknown business-state operator")
        business.append(BusinessStateExpectation(item["path"], item.get("operator", "equals"), item.get("value")))
    response = raw.get("response", {})
    return ExpectationSpec(tools, raw.get("tool_order", []), raw.get("strict_tool_order", True), business, ResponseExpectation(response.get("contains", []), response.get("not_contains", []), response.get("sources_present")))


def _parse(item: Dict[str, Any], source: str) -> ScenarioSpec:
    setup = item.get("setup", {})
    setup_obj = SetupSpec(setup.get("user_id", "test-user"), setup.get("session_id"), setup.get("users", []), setup.get("assets", []), setup.get("knowledge", []), setup.get("failures", {}))
    conversation = [ConversationStep(step["user"], _expect(step.get("expect"), source, "conversation[%d].expect" % index) if step.get("expect") else None) for index, step in enumerate(item["conversation"])]
    return ScenarioSpec(item["id"], item["name"], conversation, item.get("tags", []), setup_obj, _expect(item.get("expect"), source, "expect"), QualityExpectation(item.get("quality", {})), source)


def load_scenario_text(text: str, *, source: str = "<memory>") -> List[ScenarioSpec]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _fail(source, "$", f"invalid YAML: {exc}")
    return [_parse(item, source) for item in _validate(data, source)]


def load_scenarios(path: str | Path) -> List[ScenarioSpec]:
    target = Path(path)
    if not target.exists():
        _fail(str(target), "$", "path does not exist")
    files = sorted(target.glob("*.yaml")) + sorted(target.glob("*.yml")) if target.is_dir() else [target]
    if target.is_dir() and not files:
        _fail(str(target), "$", "no YAML files")
    if target.is_file() and target.suffix.lower() not in {".yaml", ".yml"}:
        _fail(str(target), "$", "unsupported extension")
    scenarios = []
    seen = set()
    for file in files:
        for scenario in load_scenario_text(file.read_text(encoding="utf-8"), source=str(file)):
            if scenario.id in seen:
                _fail(str(file), "id", f"duplicate scenario id: {scenario.id}")
            seen.add(scenario.id)
            scenarios.append(scenario)
    return scenarios
