from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qe_platform.adapters import ReferenceAgentAdapter
from qe_platform.reporting import build_run_report, write_html, write_json
from qe_platform.scenarios import load_scenarios
from qe_platform.workflow_runner import ScenarioRunner


def run_gate(
    *,
    asset_dir: str | Path,
    json_path: str | Path,
    html_path: str | Path,
    scenario_ids: set[str] | None = None,
    application: str = "",
    release_id: str = "",
    version: str = "",
    environment: str = "offline",
) -> int:
    scenarios = load_scenarios(asset_dir)
    if scenario_ids is not None:
        scenarios = [item for item in scenarios if item.id in scenario_ids]
    results = [ScenarioRunner(ReferenceAgentAdapter.from_setup).run(item) for item in scenarios]
    report = build_run_report(
        results,
        application=application,
        release_id=release_id,
        version=version,
        environment=environment,
    )
    write_json(report, json_path)
    write_html(report, html_path)
    return 0 if report.gate_passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline V1 API quality gate")
    parser.add_argument("--assets", default="qe_platform/scenarios/assets/reference_agent")
    parser.add_argument("--json", dest="json_path", default="reports/v1-api-e2e.json")
    parser.add_argument("--html", dest="html_path", default="reports/v1-api-e2e.html")
    parser.add_argument("--application", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--environment", default="offline")
    args = parser.parse_args(argv)
    return run_gate(
        asset_dir=args.assets,
        json_path=args.json_path,
        html_path=args.html_path,
        application=args.application,
        release_id=args.release_id,
        version=args.version,
        environment=args.environment,
    )


if __name__ == "__main__":
    sys.exit(main())
