from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence

from .config import load_config
from .reporting import write_reports
from .runner import LoadTestRunner


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone asynchronous AI application load test")
    parser.add_argument("config", help="YAML load-test configuration")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        run = asyncio.run(LoadTestRunner(config).run())
        json_path, html_path = write_reports(run)
    except (OSError, RuntimeError) as exc:
        print(f"Load test error: {exc}", file=sys.stderr)
        return 1
    print(f"Completed {run.summary.completed} requests: {run.summary.succeeded} succeeded, {run.summary.failed} failed")
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
