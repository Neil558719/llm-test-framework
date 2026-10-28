"""Versioned execution evidence. Trust comes from a separately selected plan.

Digests bind content and controlled assets; they are not signatures. In particular,
an uploaded manifest cannot establish its own authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from qe_platform.scenarios import ScenarioSpec, load_scenario_text
from qe_platform.scenarios.models import QUALITY_THRESHOLDS, validate_quality_metrics


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence must contain finite JSON values") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, **({'slots': True} if sys.version_info >= (3, 10) else {}))
class RunManifest:
    _json: str

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def asset_fingerprint(self) -> str:
        return self.as_dict()["asset_fingerprint"]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunManifest":
        if not isinstance(value, Mapping) or value.get("schema_version") != "qe-manifest-v2":
            raise ValueError("unknown manifest schema")
        rows = value.get("scenarios")
        if not isinstance(rows, list) or not rows:
            raise ValueError("manifest scenarios must be nonempty")
        specs = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("controls"), dict):
                raise ValueError("invalid manifest scenario")
            raw = dict(row["controls"], id=row.get("scenario_id"), name=row.get("scenario_id"))
            def loader_value(value):
                if isinstance(value, dict):
                    return {k: loader_value(v) for k, v in value.items()
                            if not (v is None and k in ("expect", "sources_present", "arguments_schema", "result_schema", "session_id"))}
                if isinstance(value, list):
                    return [loader_value(v) for v in value]
                return value
            specs.extend(load_scenario_text(canonical(loader_value(raw))))
        expected = freeze_run_manifest(specs, scoring_assets=value.get("scoring_assets"))
        if canonical(value) != expected._json:
            raise ValueError("manifest content or controlled asset digest differs")
        return expected


def freeze_run_manifest(scenarios: Iterable[ScenarioSpec], *, scoring_assets: Mapping[str, Any] | None = None) -> RunManifest:
    from llmtest import JudgeSpec
    from llmtest.clients.prompts import JUDGE_PROMPT, CLAIM_EXTRACTION_PROMPT, CLAIM_VERIFY_PROMPT
    rows = []
    seen = set()
    for spec in scenarios:
        if not isinstance(spec, ScenarioSpec) or not spec.id or spec.id in seen or not spec.conversation:
            raise ValueError("manifest requires unique nonempty scenarios and conversations")
        seen.add(spec.id)
        controls = {"setup": spec.setup.as_dict(), "conversation": [s.as_dict() for s in spec.conversation],
                    "expect": spec.expect.as_dict(), "quality": spec.quality.metrics}
        rows.append({"scenario_id": spec.id, "controls": controls,
                     "expected_steps": [{"index": i, "user_sha256": digest(s.user)} for i, s in enumerate(spec.conversation)],
                     "quality": [{"metric": metric, "required": True, "expectation": expectation,
                                  "threshold": expectation[QUALITY_THRESHOLDS[metric]]}
                                 for metric, expectation in sorted(spec.quality.metrics.items())],
                     "scenario_sha256": digest(controls)})
        rows[-1]["quality_policy_sha256"] = digest(rows[-1]["quality"])
    if not rows or (scoring_assets is not None and not isinstance(scoring_assets, Mapping)):
        raise ValueError("manifest requires scenarios and an object of scoring assets")
    rows.sort(key=lambda row: row["scenario_id"])
    builtins = {"integration_policy": "scenario-quality-v1", "judge_rubrics": {
        name: {"criteria": getattr(JudgeSpec, name)().criteria, "scale": getattr(JudgeSpec, name)().scale}
        for name in ("accuracy", "relevance", "faithfulness", "helpfulness")},
        "prompt_sha256": {"judge": digest(JUDGE_PROMPT), "claim_extraction": digest(CLAIM_EXTRACTION_PROMPT), "claim_verify": digest(CLAIM_VERIFY_PROMPT)},
        "hallucination_rule": "unsupported-or-contradicted/claims;empty=inconclusive"}
    assets = {"scenarios": rows, "scoring_assets": {**builtins, **dict(scoring_assets or {})}}
    return RunManifest(canonical({"schema_version": "qe-manifest-v2", **assets, "asset_fingerprint": digest(assets)}))


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be boolean")
    return value


def _assertions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("assertions must be an array of objects")
    for item in value:
        _boolean(item.get("passed"), "assertion passed")
    return value


def _quality(checks: Any, expected: list[dict[str, Any]]) -> tuple[bool, bool]:
    if not isinstance(expected, list) or any(not isinstance(c, dict) or not isinstance(c.get("metric"), str) for c in expected):
        raise ValueError("invalid required quality policy")
    for policy in expected:
        validate_quality_metrics({policy["metric"]: policy.get("expectation")})
        if policy.get("required") is not True or type(policy.get("threshold")) not in (int, float) or policy["threshold"] != policy["expectation"][QUALITY_THRESHOLDS[policy["metric"]]]:
            raise ValueError("invalid required quality threshold")
    if len({c["metric"] for c in expected}) != len(expected):
        raise ValueError("duplicate required quality policy")
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError("quality checks must be objects")
    names = [c.get("metric") for c in checks]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)) or set(names) != {c["metric"] for c in expected}:
        raise ValueError("quality checks differ from required manifest declarations")
    policies = {c["metric"]: c for c in expected}
    complete = passed = True
    for check in checks:
        policy = policies[check["metric"]]
        if check.get("required") is not True or canonical(check.get("expectation")) != canonical(policy["expectation"]):
            raise ValueError("quality declaration differs from manifest")
        threshold = check.get("threshold")
        if type(threshold) not in (int, float) or threshold != policy["threshold"]:
            raise ValueError("quality threshold differs from manifest")
        status, score = check.get("status"), check.get("score")
        if status not in ("passed", "failed", "not_executed", "inconclusive", "error"):
            raise ValueError("unknown quality status")
        if status in ("passed", "failed"):
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("evaluated quality requires a finite score in [0, 1]")
            met = score <= threshold if check["metric"] == "hallucination" else score >= threshold
            if (status == "passed") != met:
                raise ValueError("quality status contradicts threshold and score")
        elif score is not None:
            raise ValueError("unavailable quality must not claim a score")
        if any(not isinstance(check.get(key, ""), str) for key in ("provider", "model", "version", "reason")):
            raise ValueError("quality provenance labels must be strings")
        complete = complete and status in ("passed", "failed")
        passed = passed and status == "passed"
    return complete, passed


def _safe_labels(values):
    from qe_platform.telemetry.redaction import assert_sanitized_payload
    labels = {}
    for key, value in values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("provenance labels must be strings")
        try:
            assert_sanitized_payload(value)
        except ValueError:
            labels[key] = "redacted"
            labels[key + "_sha256"] = digest(value)
        else:
            labels[key] = value
    return labels


def _provenance(check):
    return _safe_labels({key: check.get(key, "") for key in ("provider", "model", "version", "reason")})


def _response_types(value):
    if not isinstance(value.get("answer"), str) or not isinstance(value.get("sources"), list) or any(not isinstance(s, str) for s in value["sources"]):
        raise ValueError("response answer/sources have invalid types")
    calls = value.get("tool_calls")
    if not isinstance(calls, list) or any(not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(c.get("arguments"), dict) for c in calls):
        raise ValueError("invalid tool call evidence")
    for key in ("metadata", "raw_response"):
        if not isinstance(value.get(key, {}), dict):
            raise ValueError("invalid response metadata")
    version = value.get("model_version")
    if version is not None and (not isinstance(version, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in version.items())):
        raise ValueError("invalid SUT version labels")
    usage = value.get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or any(type(usage.get(k, 0)) is not int or usage.get(k, 0) < 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ValueError("invalid response usage")
    for key, fields in (("latency", ("total_ms", "ttft_ms")), ("cost", ("input", "output", "total"))):
        values = value.get(key)
        if values is not None:
            if not isinstance(values, dict) or any(v is not None and (type(v) not in (int, float) or not math.isfinite(v) or v < 0) for k, v in values.items() if k in fields):
                raise ValueError("invalid response numeric evidence")


def validate_v2_report(payload: Mapping[str, Any], expected_manifest: RunManifest | Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate raw evidence, returning only a safe persistence projection."""
    from llmtest import ResponseEnvelope
    from qe_platform.workflow_runner import ScenarioRunner
    from qe_platform.scenarios.loader import _expect
    from qe_platform.workflow_runner.execution import validate_execution, execution_complete

    if payload.get("schema_version") != "qe-run-v2":
        raise ValueError("unknown run report schema")
    manifest = RunManifest.from_dict(payload.get("manifest"))
    trusted = expected_manifest is not None
    if trusted:
        expected = RunManifest.from_dict(expected_manifest.as_dict() if isinstance(expected_manifest, RunManifest) else expected_manifest)
        if expected != manifest:
            raise ValueError("report differs from independently selected manifest")
    plans = {row["scenario_id"]: row for row in manifest.as_dict()["scenarios"]}
    rows = payload.get("scenarios")
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError("scenarios must be objects")
    ids = [row.get("scenario_id") for row in rows]
    if any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or set(ids) != set(plans):
        raise ValueError("scenarios differ from manifest")
    safe_rows = []
    checker = ScenarioRunner(lambda _: None)
    for row in rows:
        plan = plans[row["scenario_id"]]
        controls = plan["controls"]
        steps = row.get("steps")
        if not isinstance(steps, list) or not steps or any(not isinstance(s, dict) for s in steps):
            raise ValueError("scenario must contain execution evidence")
        indices = [s.get("index") for s in steps]
        if any(type(i) is not int for i in indices) or indices != list(range(len(steps))) or len(steps) > len(plan["expected_steps"]):
            raise ValueError("duplicate, missing or unexpected step indices")
        calls, safe_steps = [], []
        responses = []
        for step, wanted in zip(steps, controls["conversation"]):
            status = step.get("status")
            if status not in ("passed", "failed", "error"):
                raise ValueError("unknown execution status")
            if not isinstance(step.get("error"), str):
                raise ValueError("execution error must be a string")
            if step.get("user") != wanted["user"] and not (len(steps) == 1 and status == "error" and step.get("user") == ""):
                raise ValueError("executed user input differs from controlled asset")
            assertions = _assertions(step.get("assertions"))
            if status == "error":
                if step is not steps[-1] or step.get("response") is not None or assertions:
                    raise ValueError("invalid interrupted execution evidence")
                response = None
            else:
                if step.get("error") or not isinstance(step.get("response"), dict):
                    raise ValueError("completed step requires a response")
                _response_types(step["response"])
                try:
                    response = ResponseEnvelope.from_dict(step["response"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("invalid response evidence") from exc
                actual = [a.as_dict() for a in checker._check_expectation(_expect(wanted["expect"], "manifest", "expect"), response)] if wanted["expect"] else []
                if canonical(assertions) != canonical(actual) or (status == "passed") != all(a["passed"] for a in actual):
                    raise ValueError("step assertions contradict controlled response evidence")
                calls.extend(response.tool_calls)
            responses.append(response)
            safe_steps.append({"index": step["index"], "status": status, "response_sha256": digest(step.get("response")),
                               "assertions_passed": all(a["passed"] for a in assertions),
                               "model_version": _safe_labels(response.model_version.as_dict()) if response is not None and response.model_version else None})
        execution = validate_execution(row.get('execution'), manifest.as_dict()['scoring_assets'].get('execution_policy'),
                                       expected_step_count=len(plan['expected_steps']), steps=steps)
        error = steps[-1].get("error", "")
        interrupted = steps[-1]["status"] == "error"
        executed = len(steps) == len(plan["expected_steps"]) and not interrupted
        if not executed and not interrupted:
            raise ValueError("missing steps without interrupted execution evidence")
        final = _assertions(row.get("final_assertions"))
        adapter_failed = len(steps) == 1 and steps[0]["status"] == "error" and steps[0]["user"] == ""
        actual_final = [] if adapter_failed else [a.as_dict() for a in checker._check_expectation(_expect(controls["expect"], "manifest", "expect"), responses[-1], calls, execution_error=error)]
        if interrupted:
            if not final or final[0].get("assertion_type") != "execution" or final[0]["passed"]:
                raise ValueError("interruption requires failed execution evidence")
            final = final[1:]
        if canonical(final) != canonical(actual_final):
            raise ValueError("final assertions contradict controlled response evidence")
        quality_complete, quality_passed = _quality(row.get("quality_checks"), plan["quality"])
        if executed and not "\n".join(responses[-1].sources or []).strip() and any(
            c["metric"] in ("faithfulness", "hallucination") and c["status"] in ("passed", "failed") for c in row["quality_checks"]
        ):
            raise ValueError("missing grounding cannot supply evaluated quality evidence")
        if not executed and any(c["status"] != "not_executed" for c in row["quality_checks"]):
            raise ValueError("interrupted execution cannot supply final quality evidence")
        complete = executed and quality_complete and execution_complete(execution)
        passed = complete and all(s["status"] == "passed" for s in steps) and all(a["passed"] for a in final) and quality_passed
        if _boolean(row.get("complete"), "complete") != complete or _boolean(row.get("passed"), "passed") != passed:
            raise ValueError("scenario completion/pass contradicts manifest evidence")
        safe_rows.append({"scenario_id": row["scenario_id"], "expected_step_count": len(plan["expected_steps"]),
                          "steps": safe_steps, "final_assertions_passed": all(a["passed"] for a in final),
                          "quality": [{**{k: c[k] for k in ("metric", "required", "expectation", "threshold", "status", "score")}, **_provenance(c)} for c in row["quality_checks"]],
                          "expected_quality": plan["quality"], "complete": complete, "passed": passed})
        if execution is not None:
            safe_rows[-1]['execution'] = execution
    complete = all(r["complete"] for r in safe_rows)
    passed = sum(r["passed"] for r in safe_rows)
    for key, value in (("total", len(rows)), ("passed", passed), ("failed", len(rows) - passed)):
        if type(payload.get(key)) is not int or payload[key] != value:
            raise ValueError("run counts contradict manifest evidence")
    gate = complete and passed == len(rows)
    if _boolean(payload.get("complete"), "complete") != complete or _boolean(payload.get("gate_passed"), "gate_passed") != gate:
        raise ValueError("run gate/completion contradict manifest evidence")
    evidence = {"schema_version": "qe-evidence-v2", "scenarios": sorted(safe_rows, key=lambda r: r["scenario_id"])}
    evidence["sha256"] = digest(evidence)
    return {"complete": complete, "asset_fingerprint": manifest.asset_fingerprint,
            "manifest_sha256": digest(manifest.as_dict()), "verification": "verified_v2" if trusted else "unverified_manifest",
            "evidence": evidence}


def validate_stored_evidence(run: Any) -> None:
    """Recheck persisted projection, including completion, before release use."""
    from qe_platform.workflow_runner.execution import validate_execution, execution_complete
    if run.verification not in ("legacy_unverified", "unverified_manifest", "verified_v2"):
        raise ValueError("unknown stored verification schema")
    if run.verification == "legacy_unverified":
        if run.complete is not None or run.evidence is not None or run.asset_fingerprint or run.manifest_sha256:
            raise ValueError("legacy report cannot claim v2 evidence")
        return
    evidence = run.evidence
    if not isinstance(evidence, dict) or evidence.get("schema_version") != "qe-evidence-v2":
        raise ValueError("invalid stored execution proof")
    if evidence.get("sha256") != digest({k: v for k, v in evidence.items() if k != "sha256"}):
        raise ValueError("stored execution proof content differs")
    for value in (run.content_sha256, run.asset_fingerprint, run.manifest_sha256):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid stored proof digest")
    rows = evidence.get("scenarios")
    if not isinstance(rows, list) or not rows or tuple(r.get("scenario_id") for r in rows) != run.scenario_ids:
        raise ValueError("stored proof scenario coverage differs")
    for row in rows:
        qc, qp = _quality(row.get("quality"), row.get("expected_quality"))
        steps = row.get("steps")
        if not isinstance(steps, list) or not steps or [s.get("index") for s in steps] != list(range(len(steps))):
            raise ValueError("invalid stored execution coverage")
        if any(s.get("status") not in ("passed", "failed", "error") for s in steps):
            raise ValueError("unknown stored execution status")
        execution = row.get('execution')
        validate_execution(execution, execution.get('policy') if isinstance(execution, dict) else None,
                           expected_step_count=row['expected_step_count'], steps=steps)
        complete = len(steps) == row["expected_step_count"] and all(s["status"] != "error" for s in steps) and qc and execution_complete(execution)
        passed = complete and all(s["status"] == "passed" and _boolean(s["assertions_passed"], "assertions_passed") for s in steps) and _boolean(row["final_assertions_passed"], "final_assertions_passed") and qp
        if type(row.get("complete")) is not bool or row["complete"] != complete or type(row.get("passed")) is not bool or row["passed"] != passed:
            raise ValueError("stored scenario proof contradicts execution")
    if type(run.complete) is not bool or run.complete != all(r["complete"] for r in rows) or run.passed != sum(r["passed"] for r in rows) or run.total != len(rows) or run.gate_passed != (run.complete and run.passed == run.total):
        raise ValueError("stored run proof contradicts execution")