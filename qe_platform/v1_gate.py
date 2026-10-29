from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Callable

from qe_platform.adapters import ReferenceAgentAdapter
from qe_platform.reporting import build_run_report, write_html, write_json
from qe_platform.reporting.integrity import freeze_run_manifest
from qe_platform.scenarios import load_scenarios
from qe_platform.scenarios import ScenarioSpec
from llmtest import ResponseEnvelope
from qe_platform.workflow_runner import QualityCheckResult, ScenarioRunner


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
    quality_evaluator: Callable[[ScenarioSpec, ResponseEnvelope], list[QualityCheckResult]] | None = None,
) -> int:
    scenarios = load_scenarios(asset_dir)
    if scenario_ids is not None:
        scenarios = [item for item in scenarios if item.id in scenario_ids]
    manifest = freeze_run_manifest(scenarios) if scenarios else None
    results = [ScenarioRunner(ReferenceAgentAdapter.from_setup, quality_evaluator=quality_evaluator).run(item) for item in scenarios]
    report = build_run_report(
        results,
        application=application,
        release_id=release_id,
        version=version,
        environment=environment,
        manifest=manifest,
    )
    write_json(report, json_path)
    write_html(report, html_path)
    return 0 if report.gate_passed else 1


async def run_gate_async(
    *, asset_dir: str | Path, json_path: str | Path, html_path: str | Path,
    budget, max_concurrency=4, adapter='reference-agent', adapter_factory=None,
    dify_config=None, scenario_ids=None, application='', release_id='', version='', environment='offline',
    quality_evaluator=None,
) -> int:
    """Freeze policy before execution, then run real native adapters and v2 reports."""
    from qe_platform.adapters import AsyncDifyAdapter, AsyncReferenceAgentAdapter
    from qe_platform.workflow_runner import AsyncScenarioRunner
    if adapter not in ('reference-agent', 'dify'):
        raise ValueError('unknown async adapter')
    if adapter_factory is None:
        if adapter == 'reference-agent':
            adapter_factory = AsyncReferenceAgentAdapter.from_setup
        else:
            adapter_factory = lambda _: AsyncDifyAdapter(dify_config) if dify_config is not None else AsyncDifyAdapter.from_environment()
    runner = AsyncScenarioRunner(adapter_factory, max_concurrency=max_concurrency, quality_evaluator=quality_evaluator)
    scenarios = load_scenarios(asset_dir)
    if scenario_ids is not None:
        scenarios = [item for item in scenarios if item.id in scenario_ids]
    manifest = freeze_run_manifest(scenarios, scoring_assets={'execution_policy': budget.policy(max_concurrency)}) if scenarios else None
    results = await runner.run_many(scenarios, budget=budget)
    report = build_run_report(results, application=application, release_id=release_id, version=version,
                              environment=environment, manifest=manifest)
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
    parser.add_argument('--async', dest='async_mode', action='store_true')
    parser.add_argument('--adapter', choices=('reference-agent', 'dify'), default='reference-agent')
    parser.add_argument('--case-timeout', type=float)
    parser.add_argument('--max-attempts', type=int)
    parser.add_argument('--max-concurrency', type=int)
    parser.add_argument('--retry-backoff', type=float)
    args = parser.parse_args(argv)
    if args.async_mode:
        from qe_platform.workflow_runner import ExecutionBudget
        return asyncio.run(run_gate_async(asset_dir=args.assets, json_path=args.json_path, html_path=args.html_path,
            application=args.application, release_id=args.release_id, version=args.version, environment=args.environment,
            adapter=args.adapter, max_concurrency=args.max_concurrency if args.max_concurrency is not None else 4,
            budget=ExecutionBudget(case_timeout_s=args.case_timeout if args.case_timeout is not None else 30,
                max_attempts=args.max_attempts if args.max_attempts is not None else 1,
                retry_backoff_s=args.retry_backoff if args.retry_backoff is not None else 0)))
    if args.adapter != 'reference-agent' or any(value is not None for value in (args.case_timeout, args.max_attempts, args.max_concurrency, args.retry_backoff)):
        parser.error('async adapter and budget options require --async')
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
