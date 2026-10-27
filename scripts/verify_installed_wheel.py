"""Check installed package resources and the offline API gate outside source imports."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import sysconfig


EXPECTED_SCENARIO_IDS = {
    "access-create", "access-multiturn", "access-handoff", "access-user-missing", "access-service-5xx",
    "knowledge-hit", "knowledge-refusal", "knowledge-timeout",
    "ticket-create", "ticket-asset-required", "ticket-user-missing", "ticket-owner-denied",
    "ticket-idempotent", "ticket-service-5xx",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/installed-wheel"))
    args = parser.parse_args()
    # This consumer check must never select a real model or telemetry endpoint.
    os.environ["REFERENCE_AGENT_MODEL_MODE"] = "mock"
    os.environ["QE_TELEMETRY_ENDPOINT"] = ""

    import llmtest
    import qe_platform
    import reference_agent
    from fastapi.testclient import TestClient
    from qe_platform.v1_gate import run_gate
    from reference_agent.app import create_app

    installed_root = Path(sys.prefix).resolve()
    package_roots = {Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")}
    for module in (llmtest, qe_platform, reference_agent):
        location = Path(module.__file__).resolve()
        if installed_root not in location.parents or not any(root in location.parents for root in package_roots):
            raise RuntimeError(f"expected an installed wheel import: {location}")

    with TestClient(create_app(":memory:")) as client:
        web = Path(reference_agent.__file__).resolve().parent / "web"
        for route, name in (("/", "index.html"), ("/app.js", "app.js"), ("/styles.css", "styles.css")):
            response = client.get(route)
            if response.status_code != 200 or response.content != (web / name).read_bytes():
                raise RuntimeError(f"installed web asset is unavailable: {route}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    version = importlib.metadata.version("llmtest")
    result = run_gate(
        asset_dir=Path(qe_platform.__file__).resolve().parent / "scenarios/assets/reference_agent",
        json_path=args.output_dir / "gate.json",
        html_path=args.output_dir / "gate.html",
        application="reference_agent",
        version=version,
        environment="installed-wheel-mock",
    )
    report = json.loads((args.output_dir / "gate.json").read_text(encoding="utf-8"))
    if report.get("schema_version") != "qe-run-v2" or report.get("verification") != "verified_v2" or report.get("release_eligible") is not True:
        raise RuntimeError("installed native gate did not produce complete verified v2 evidence")
    actual_ids = [scenario["scenario_id"] for scenario in report["scenarios"]]
    if set(actual_ids) != EXPECTED_SCENARIO_IDS or len(actual_ids) != len(EXPECTED_SCENARIO_IDS):
        raise RuntimeError(f"installed scenario coverage differs: expected {sorted(EXPECTED_SCENARIO_IDS)}, got {sorted(actual_ids)}")
    print(json.dumps({"version": version, "passed": report["passed"], "total": report["total"], "gate_exit": result}))
    return result


if __name__ == "__main__":
    raise SystemExit(main())