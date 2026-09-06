"""Orchestrate fault and recovery load-test phases for a gate suite."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from .gate_models import GateCheck, GateScenarioResult, GateSuiteConfig, GateSuiteResult
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

    async def _verify_database_recovery(
        self,
        config: LoadTestConfig,
        recovery_run: LoadTestRun,
    ) -> GateCheck:
        expected = len(recovery_run.samples)
        session_ids = [
            sample.conversation_id
            for sample in recovery_run.samples
            if sample.conversation_id
        ]
        found = 0
        parsed = urlsplit(config.target_url)
        base_path = parsed.path.rstrip("/")
        async with self.client_factory(
            headers=dict(config.headers),
            timeout=config.timeout_seconds,
        ) as client:
            for session_id in session_ids:
                session_path = f"{base_path}/api/sessions/{quote(session_id, safe='')}"
                session_url = urlunsplit(
                    (parsed.scheme, parsed.netloc, session_path, "", "")
                )
                try:
                    response = await client.get(session_url)
                    payload = response.json() if response.status_code == 200 else {}
                    if (
                        isinstance(payload, Mapping)
                        and payload.get("session_id") == session_id
                    ):
                        found += 1
                except (httpx.HTTPError, ValueError, TypeError):
                    continue
        passed = found == expected
        return GateCheck(
            name="database_recovery_session_count",
            stage="recovery",
            operator="==",
            expected=expected,
            actual=found,
            unit="sessions",
            passed=passed,
            reason=(
                f"persisted recovery sessions {found} == expected {expected}"
                if passed
                else f"persisted recovery sessions {found} != expected {expected}"
            ),
        )

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
                if scenario.fault.type == "database_error":
                    checks.append(
                        await self._verify_database_recovery(
                            scenario.load,
                            recovery_run,
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
