"""Orchestrate fault and recovery load-test phases for a gate suite."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx

from .gate_models import GateScenarioResult, GateSuiteConfig, GateSuiteResult
from .gates import evaluate_samples, evaluate_thresholds
from .models import LoadTestConfig, LoadTestRun
from .runner import LoadTestRunner


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GateSuiteRunner:
    def __init__(
        self,
        config: GateSuiteConfig,
        *,
        client_factory: Callable[..., Any] = httpx.AsyncClient,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.client_factory = client_factory
        self.environ = os.environ if environ is None else environ

    async def _run_load(self, config: LoadTestConfig) -> LoadTestRun:
        return await LoadTestRunner(
            config,
            client_factory=self.client_factory,
        ).run()

    async def run(self) -> GateSuiteResult:
        token = self.environ.get(self.config.fault_token_env, "")
        if not token:
            raise ValueError(
                f"fault token environment variable is missing: {self.config.fault_token_env}"
            )
        started_at = _utc_now()
        results: list[GateScenarioResult] = []
        for scenario in self.config.scenarios:
            fault_headers = {
                **scenario.load.headers,
                "X-QE-Test-Token": token,
                "X-QE-Fault": json.dumps(
                    scenario.fault.as_dict(), separators=(",", ":")
                ),
            }
            fault_run = await self._run_load(
                replace(scenario.load, headers=fault_headers)
            )
            checks = evaluate_samples(fault_run.samples, scenario.expect, "fault")
            recovery_run = None
            if scenario.recovery:
                recovery_run = await self._run_load(scenario.load)
                checks.extend(
                    evaluate_samples(
                        recovery_run.samples,
                        scenario.recovery_expect,
                        "recovery",
                    )
                )
                checks.extend(
                    evaluate_thresholds(
                        recovery_run.summary,
                        scenario.thresholds,
                        "recovery",
                    )
                )
            results.append(
                GateScenarioResult(
                    scenario_id=scenario.id,
                    fault_type=scenario.fault.type,
                    fault_run=fault_run,
                    recovery_run=recovery_run,
                    checks=checks,
                )
            )
        return GateSuiteResult(
            config=self.config,
            started_at=started_at,
            finished_at=_utc_now(),
            scenarios=results,
        )
