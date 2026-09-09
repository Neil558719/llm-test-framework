from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .engine import build_quality_links, build_trends, validate_release
from .models import ReleaseGatePolicy
from .reporting import write_quality_html, write_quality_json
from .storage import SQLiteQualityRepository


def _repository(args: argparse.Namespace) -> SQLiteQualityRepository:
    return SQLiteQualityRepository(args.database, retention_days=args.retention_days)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True)
    parser.add_argument("--retention-days", type=int, default=30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the M17 online/offline quality loop")
    commands = parser.add_subparsers(dest="command", required=True)

    import_run = commands.add_parser("import-run", help="import a sanitized offline RunReport")
    _add_common(import_run)
    import_run.add_argument("--report", required=True)
    import_run.add_argument("--source-label", default="cli-report")

    link = commands.add_parser("link", help="link a promoted online sample to an offline run")
    _add_common(link)
    link.add_argument("--promotion-id", required=True)
    link.add_argument("--offline-run-id", required=True)

    trends = commands.add_parser("trends", help="write trend and link evidence")
    _add_common(trends)
    trends.add_argument("--json", dest="json_path", required=True)
    trends.add_argument("--html", dest="html_path", required=True)
    trends.add_argument("--application", default="")
    trends.add_argument("--version", default="")

    validation = commands.add_parser("validate-release", help="run a baseline/candidate release gate")
    _add_common(validation)
    validation.add_argument("--baseline", required=True)
    validation.add_argument("--candidate", required=True)
    validation.add_argument("--json", dest="json_path", required=True)
    validation.add_argument("--html", dest="html_path", required=True)
    validation.add_argument("--max-candidate-failure-rate", type=float, default=0.0)
    validation.add_argument("--max-pass-rate-drop", type=float, default=0.0)
    validation.add_argument("--max-low-quality-rate-increase", type=float, default=0.0)
    validation.add_argument("--application", default="")
    validation.add_argument("--release-id", default="")
    validation.add_argument("--allow-incomplete", dest="require_complete", action="store_false")
    validation.set_defaults(require_complete=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository: SQLiteQualityRepository | None = None
    try:
        repository = _repository(args)
        if args.command == "import-run":
            payload = json.loads(Path(args.report).read_text(encoding="utf-8"))
            run = repository.import_run(payload, source_label=args.source_label)
            print(json.dumps(run.as_dict(), ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "link":
            link = repository.create_link(args.promotion_id, args.offline_run_id)
            print(json.dumps(link.as_dict(), ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "trends":
            payload: dict[str, Any] = {
                "trends": [item.as_dict() for item in build_trends(repository, application=args.application, version=args.version)],
                "links": [item.as_dict() for item in build_quality_links(repository)],
            }
            write_quality_json(payload, args.json_path)
            write_quality_html(payload, args.html_path)
            return 0
        policy = ReleaseGatePolicy(
            max_candidate_failure_rate=args.max_candidate_failure_rate,
            max_pass_rate_drop=args.max_pass_rate_drop,
            max_low_quality_rate_increase=args.max_low_quality_rate_increase,
            require_complete=args.require_complete,
            application=args.application,
            release_id=args.release_id,
        )
        result = validate_release(repository, args.baseline, args.candidate, policy)
        payload = result.as_dict()
        payload["links"] = [item.as_dict() for item in build_quality_links(repository, offline_run_id=args.candidate)]
        write_quality_json(payload, args.json_path)
        write_quality_html(payload, args.html_path)
        return 0 if result.passed else 1
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if repository is not None:
            repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
