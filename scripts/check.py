"""Explicit offline test tiers. Collection is evidence, never an execution pass.

Run from any working directory with --tier smoke|core|full --mode offline|live.
Live provider, UI, browser, container and host-system acceptance are separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def offline_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if any(part in upper for part in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')) or upper.startswith(
                ('LLM_', 'OPENAI_', 'ANTHROPIC_', 'DIFY_', 'QE_', 'REFERENCE_AGENT_',
                 'PYTEST_', 'CHECK_', 'LANGSMITH_', 'LANGCHAIN_')) or upper in ('PYTHONPATH', 'PYTHONHOME'):
            env.pop(key)
    env.update(LLM_MODE='mock', LLM_TEST_MODE='mock', REFERENCE_AGENT_MODEL_MODE='mock',
        REFERENCE_AGENT_MODEL_PROVIDER='mock',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
        PYTHONDONTWRITEBYTECODE='1')
    return env


def matches(nodeid: str, prefix: str) -> bool:
    return nodeid == prefix or nodeid.startswith(prefix + '[')


def exclusion(nodeid: str, manifest: dict, tier: str) -> str | None:
    file = nodeid.split('::')[0]
    if file in manifest['excluded_files']:
        return manifest['excluded_files'][file]
    for prefix, reason in manifest['excluded_nodes'].items():
        if matches(nodeid, prefix):
            return reason
    for prefix, spec in manifest['platform_nodes'].items():
        if matches(nodeid, prefix):
            available = {'powershell': bool(shutil.which('powershell.exe') or shutil.which('pwsh')),
                         'posix': os.name != 'nt' and bool(shutil.which('sh'))}
            if not available[spec['requires']]:
                return spec['reason']
    if tier == 'smoke' and nodeid not in manifest['smoke']:
        return 'outside smoke manifest'
    if tier == 'core' and file not in manifest['core']:
        return 'outside core manifest'
    return None


def validate_manifest(root: Path, manifest: dict) -> None:
    required = {'schema_version', 'files', 'smoke', 'core', 'excluded_nodes', 'excluded_files',
                'platform_nodes', 'requirements', 'plugins', 'assets'}
    if set(manifest) != required or manifest['schema_version'] != 1:
        raise ValueError('unsupported check manifest schema')
    for key in ('files', 'smoke', 'core', 'requirements', 'plugins', 'assets'):
        values = manifest[key]
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
            raise ValueError('invalid or duplicate manifest entries: ' + key)
    for key in ('excluded_nodes', 'excluded_files', 'platform_nodes'):
        if not isinstance(manifest[key], dict):
            raise ValueError('invalid manifest mapping: ' + key)
    actual = sorted(p.relative_to(root).as_posix() for p in (root / 'tests').rglob('test_*.py'))
    if actual != sorted(manifest['files']):
        raise ValueError('manifest file inventory differs: unclassified=' + str(sorted(set(actual) - set(manifest['files'])))
                         + '; missing=' + str(sorted(set(manifest['files']) - set(actual))))
    if not manifest['files'] or not manifest['smoke'] or not manifest['core']:
        raise ValueError('empty required tier manifest')
    for file in [*manifest['core'], *manifest['excluded_files']]:
        if file not in manifest['files']:
            raise ValueError('unknown manifest file: ' + file)
    for mapping in ('excluded_nodes', 'excluded_files'):
        if any(not isinstance(reason, str) or not reason.strip() for reason in manifest[mapping].values()):
            raise ValueError('exclusions require explicit reasons')
    for spec in manifest['platform_nodes'].values():
        if set(spec) != {'requires', 'reason'} or spec['requires'] not in ('powershell', 'posix') or not spec['reason']:
            raise ValueError('unsupported platform prerequisite')


def validate_inventory(nodeids: list[str], manifest: dict) -> None:
    if len(set(nodeids)) != len(nodeids):
        raise ValueError('duplicate collected node IDs')
    for file in manifest['files']:
        if not any(node.split('::')[0] == file for node in nodeids):
            raise ValueError('declared test file collected no nodes: ' + file)
    for node in manifest['smoke']:
        if node not in nodeids:
            raise ValueError('unknown smoke node: ' + node)
        if exclusion(node, manifest, 'smoke') is not None:
            raise ValueError('required smoke node cannot be excluded: ' + node)
    for prefix in [*manifest['excluded_nodes'], *manifest['platform_nodes']]:
        if not any(matches(node, prefix) for node in nodeids):
            raise ValueError('unknown manifest node: ' + prefix)


def execution_errors(selected: list[str], events: list[dict]) -> list[str]:
    errors = []
    if set(selected) != {event['nodeid'] for event in events}:
        errors.append('selected and executed node inventories differ')
    for node in selected:
        records = [event for event in events if event['nodeid'] == node]
        if Counter(event['phase'] for event in records) != Counter({'setup': 1, 'call': 1, 'teardown': 1}):
            errors.append('incomplete or repeated execution: ' + node)
        if any(event['outcome'] != 'passed' or event['wasxfail'] for event in records):
            errors.append('failure, unexpected skip or xfail: ' + node)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tier', choices=('smoke', 'core', 'full'), required=True)
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--collect-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = (args.out or root / 'reports' / ('check-' + args.tier + '-' + args.mode)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 'check-report-v1', 'tier': args.tier, 'mode': args.mode,
        'status': 'not-run', 'selected': [], 'excluded': [], 'executed': [], 'errors': [],
        'commands': [], 'resource_checks': [], 'exit': 2, 'python': sys.version.split()[0],
        'counts': {'selected': 0, 'excluded': 0, 'executed': 0, 'passed': 0},
        'boundary': 'Local test evidence only; UI, live providers, containers and host-system acceptance are separate'}

    def finish(code: int) -> int:
        report['exit'] = code
        write_json(out / 'check-report.json', report)
        print(json.dumps({'status': report['status'], 'counts': report['counts'],
            'errors': report['errors'], 'report': str(out / 'check-report.json')}, ensure_ascii=False))
        return code

    # A live suite and its target/budget have not been declared by this task.
    # Do not let inherited credentials or skipped examples count as acceptance.
    if args.mode == 'live':
        report['errors'].append('not-run: live target, request budget and dedicated acceptance suite must be explicitly configured')
        return finish(2)
    report['status'] = 'failed'
    try:
        manifest = json.loads((root / 'scripts/check-manifest.json').read_text(encoding='utf-8'))
        validate_manifest(root, manifest)
        for requirement in manifest['requirements']:
            importlib.metadata.version(requirement)
        if args.tier == 'full':
            for name in manifest['assets']:
                path = root / name
                if not path.is_file() or not path.stat().st_size:
                    raise ValueError('missing or empty required asset: ' + name)
                report['resource_checks'].append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    except (ValueError, OSError, importlib.metadata.PackageNotFoundError) as error:
        report['errors'].append(str(error))
        return finish(2)
    env = offline_environment()
    settings = out / 'settings.json'
    env['CHECK_SETTINGS_FILE'] = str(settings)
    base_command = [sys.executable, '-B', '-m', 'pytest', '-q', '-o', 'addopts=',
        '--rootdir=' + str(root), '--confcutdir=' + str(root), '-p', 'scripts.check_plugin']
    for plugin in manifest['plugins']:
        base_command.extend(['-p', plugin])
    base_command.extend(['tests'])

    def invoke(phase: str) -> tuple[int, dict]:
        output = out / (phase + '.json')
        output.unlink(missing_ok=True)
        write_json(settings, {'manifest': manifest, 'tier': args.tier, 'phase': phase, 'output': str(output)})
        command = [*base_command, '--junitxml=' + str(out / (phase + '.xml'))]
        if phase == 'collection':
            command.append('--collect-only')
        report['commands'].append({'phase': phase, 'argv': command})
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')
        (out / (phase + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        (out / (phase + '.exit')).write_text(str(result.returncode) + '\n', encoding='utf-8')
        report['commands'][-1]['exit'] = result.returncode
        if not output.is_file():
            raise ValueError(phase + ' did not produce an inventory; see its log')
        return result.returncode, json.loads(output.read_text(encoding='utf-8'))

    try:
        code, collected = invoke('collection')
        report['selected'] = collected['selected']
        report['excluded'] = collected['excluded']
        report['counts'].update(selected=len(report['selected']), excluded=len(report['excluded']))
        if code or collected['errors']:
            report['errors'].extend(collected['errors'] or ['collection process failed'])
            return finish(1)
        if not report['selected']:
            raise ValueError('empty test selection')
        if args.collect_only:
            report['status'] = 'collected'
            return finish(0)
        code, execution = invoke('execution')
        report['executed'] = execution['events']
        report['errors'].extend(execution['errors'])
        if (execution['selected'] != collected['selected'] or execution['excluded'] != collected['excluded']):
            report['errors'].append('collection inventory changed before execution')
        report['errors'].extend(execution_errors(report['selected'], execution['events']))
        report['counts']['executed'] = len({e['nodeid'] for e in execution['events']})
        report['counts']['passed'] = sum(
            all(e['outcome'] == 'passed' and not e['wasxfail'] for e in execution['events'] if e['nodeid'] == node)
            and Counter(e['phase'] for e in execution['events'] if e['nodeid'] == node) == Counter({'setup': 1, 'call': 1, 'teardown': 1})
            for node in report['selected'])
        if code:
            report['errors'].append('execution process exited nonzero: ' + str(code))
        if report['errors']:
            return finish(1)
    except (ValueError, OSError, KeyError) as error:
        report['errors'].append(str(error))
        return finish(2)
    report['status'] = 'passed'
    return finish(0)


if __name__ == '__main__':
    raise SystemExit(main())