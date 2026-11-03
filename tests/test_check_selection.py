"""Black-box checks using tiny isolated suites, never the repository root suite."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def suite(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('check.py', 'check_plugin.py'):
        shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
    (tmp_path / 'tests').mkdir()
    return tmp_path


def run(suite, body='def test_ok():\n    assert True\n', *, tier='full', mode='offline',
        change=None, extra=(), env_extra=None):
    (suite / 'tests/test_sample.py').write_text(body, encoding='utf-8')
    manifest = {'schema_version': 1, 'files': ['tests/test_sample.py'],
        'smoke': ['tests/test_sample.py::test_ok'], 'core': ['tests/test_sample.py'],
        'excluded_nodes': {}, 'excluded_files': {}, 'platform_nodes': {},
        'requirements': ['pytest'], 'plugins': [], 'assets': []}
    if change:
        manifest.update(change)
    (suite / 'scripts/check-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    env = dict(os.environ)
    # The parent pytest invocation may explicitly disable autoload. The runner
    # must still load its own declared plugins without inheriting selection args.
    env.update(env_extra or {})
    result = subprocess.run([sys.executable, str(suite / 'scripts/check.py'),
        '--tier', tier, '--mode', mode, '--out', str(suite / 'out'), *extra],
        cwd=suite, env=env, capture_output=True, text=True, encoding='utf-8')
    report_path = suite / 'out/check-report.json'
    assert report_path.is_file(), result.stdout + result.stderr
    evidence = os.environ.get('CHECK_SELECTION_EVIDENCE')
    if evidence:
        destination = Path(evidence) / suite.name
        shutil.copytree(suite / 'out', destination, dirs_exist_ok=True)
        (destination / 'cli-exit.txt').write_text(str(result.returncode), encoding='utf-8')
        (destination / 'cli-console.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    return result, json.loads(report_path.read_text(encoding='utf-8'))


def test_small_smoke_has_complete_selected_and_excluded_inventory(suite):
    result, report = run(suite, 'def test_ok(): pass\ndef test_other(): assert False\n', tier='smoke')
    assert result.returncode == 0, result.stdout + result.stderr
    assert report['status'] == 'passed'
    assert report['selected'] == ['tests/test_sample.py::test_ok']
    assert report['excluded'] == [{'nodeid': 'tests/test_sample.py::test_other', 'reason': 'outside smoke manifest'}]
    assert report['counts']['passed'] == 1


@pytest.mark.parametrize('body', [
    'def test_ok(): assert False\n',
    'import pytest\ndef test_ok(): pytest.skip("missing prerequisite")\n',
    'import pytest\n@pytest.mark.xfail\ndef test_ok(): assert False\n',
    'import pytest\n@pytest.mark.xfail\ndef test_ok(): pass\n',
    'import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError("setup")\ndef test_ok(broken): pass\n',
    'import pytest\n@pytest.fixture\ndef broken():\n yield\n raise RuntimeError("teardown")\ndef test_ok(broken): pass\n',
])
def test_failed_skipped_or_incomplete_execution_never_passes(suite, body):
    result, report = run(suite, body)
    assert result.returncode != 0
    assert report['status'] == 'failed'


@pytest.mark.parametrize('body', [
    'raise RuntimeError("collection")\n',
    'import definitely_missing_x02_dependency\n',
    'import pytest\npytest.importorskip("definitely_missing_x02_dependency")\n',
])
def test_collection_errors_or_collection_skips_are_not_green(suite, body):
    result, report = run(suite, body)
    assert result.returncode != 0
    assert report['status'] == 'failed' and report['errors']


@pytest.mark.parametrize('change', [
    {'smoke': []}, {'smoke': ['tests/test_sample.py::test_missing']},
    {'files': ['tests/test_missing.py']}, {'core': ['tests/test_missing.py']},
    {'excluded_nodes': {'tests/test_sample.py::test_missing': 'stale entry'}},
    {'requirements': ['definitely-missing-x02-distribution']},
])
def test_empty_stale_or_missing_required_manifest_entries_fail(suite, change):
    result, report = run(suite, tier='smoke', change=change)
    assert result.returncode != 0
    assert report['status'] == 'failed' and report['errors']


def test_unclassified_new_test_file_is_visible_failure(suite):
    (suite / 'tests/test_new.py').write_text('def test_new(): pass\n', encoding='utf-8')
    result, report = run(suite)
    assert result.returncode != 0
    assert 'manifest file inventory differs' in ' '.join(report['errors'])


def test_collect_only_cannot_claim_execution_passed(suite):
    result, report = run(suite, extra=['--collect-only'])
    assert result.returncode == 0
    assert report['status'] == 'collected'
    assert report['executed'] == [] and report['counts']['passed'] == 0


def test_offline_scrubs_credentials_provider_config_and_pytest_filters(suite):
    body = '''import os
def test_ok():
    assert os.environ["LLM_MODE"] == "mock"
    assert os.environ["LLM_TEST_MODE"] == "mock"
    assert os.environ["REFERENCE_AGENT_MODEL_MODE"] == "mock"
    for name in ("DIFY_AGENT_KEY", "LLM_APP_MODEL", "LLM_API_KEY", "OPENAI_API_KEY", "PYTEST_ADDOPTS", "REFERENCE_AGENT_MODEL"):
        assert name not in os.environ
'''
    result, report = run(suite, body, env_extra={'DIFY_AGENT_KEY': 'synthetic',
        'LLM_APP_MODEL': 'synthetic', 'LLM_MODE': 'real', 'LLM_API_KEY': 'synthetic',
        'OPENAI_API_KEY': 'synthetic', 'REFERENCE_AGENT_MODEL': 'synthetic-model',
        'PYTEST_ADDOPTS': '-k nonexistent --reruns 1'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert report['counts']['passed'] == 1


def test_assertion_is_executed_once_without_rerun(suite):
    body = '''from pathlib import Path
def test_ok():
    count = Path("attempts")
    old = int(count.read_text()) if count.exists() else 0
    count.write_text(str(old + 1))
    assert old > 0
'''
    result, report = run(suite, body)
    assert result.returncode != 0 and report['status'] == 'failed'
    assert (suite / 'attempts').read_text() == '1'


def test_missing_full_asset_fails_before_execution(suite):
    result, report = run(suite, change={'assets': ['missing.yaml']})
    assert result.returncode != 0 and report['errors']
    assert report['executed'] == []


def test_explicit_environment_exclusion_does_not_execute_node(suite):
    result, report = run(suite, 'def test_ok(): pass\ndef test_host(): assert False\n',
        change={'excluded_nodes': {'tests/test_sample.py::test_host': 'separate host acceptance'}})
    assert result.returncode == 0
    assert report['excluded'] == [{'nodeid': 'tests/test_sample.py::test_host', 'reason': 'separate host acceptance'}]


def test_live_without_declared_target_is_not_run_and_nonzero(suite):
    result, report = run(suite, mode='live')
    assert result.returncode != 0 and report['status'] == 'not-run'
    assert report['executed'] == [] and report['errors']


def test_zero_process_exit_without_execution_evidence_is_failure(suite):
    result, report = run(suite, 'import os\ndef test_ok(): os._exit(0)\n')
    assert result.returncode != 0 and report['status'] == 'failed'
    assert 'did not produce an inventory' in ' '.join(report['errors'])


def test_node_disappearing_between_collection_and_execution_is_failure(suite):
    body = '''from pathlib import Path
first = not Path("collected_once").exists()
Path("collected_once").write_text("yes")
def test_ok(): pass
if first:
    def test_other(): pass
'''
    result, report = run(suite, body)
    assert result.returncode != 0 and report['status'] == 'failed'
    assert 'collection inventory changed' in ' '.join(report['errors'])


def test_redeclaring_a_smoke_requirement_as_excluded_is_failure(suite):
    result, report = run(suite, 'def test_ok(): pass\ndef test_other(): pass\n', tier='smoke',
        change={'smoke': ['tests/test_sample.py::test_ok', 'tests/test_sample.py::test_other'],
                'excluded_nodes': {'tests/test_sample.py::test_other': 'cannot silently omit required smoke'}})
    assert result.returncode != 0 and report['errors']