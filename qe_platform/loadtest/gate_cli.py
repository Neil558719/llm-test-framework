"""Command-line entry point for milestone 13 quality gates."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence

from .gate_config import load_gate_config
from .gate_reporting import write_gate_reports
from .gate_runner import GateSuiteRunner


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fault injection, recovery, SLA/SLO, and cost quality gate"
    )
    parser.add_argument("config", help="YAML gate-suite configuration")
    args = parser.parse_args(argv)
    try:
        config = load_gate_config(args.config)
        result = asyncio.run(GateSuiteRunner(config).run())
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f"Gate execution error: {exc}", file=sys.stderr)
        return 1
    try:
        json_path, html_path = write_gate_reports(result)
    except (OSError, RuntimeError) as exc:
        print(f"Gate execution error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Completed {len(result.scenarios)} scenarios: "
        f"{result.passed_scenarios} passed, "
        f"{len(result.scenarios) - result.passed_scenarios} failed"
    )
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")
    if not result.gate_passed:
        print(
            f"Gate failed: {result.failed_checks} checks failed",
            file=sys.stderr,
        )
        return 3
    print("Gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
