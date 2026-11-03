"""Expected RED against the unchanged legacy runner; never part of green tiers.

Run with pytest explicitly. These isolated synthetic suites make no model calls.
The two failures preserve why process exit zero alone is insufficient.
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def legacy(tmp_path, option):
    env = dict(os.environ, LLM_MODE='mock', LLM_TEST_MODE='mock')
    return subprocess.run([sys.executable, str(ROOT / 'scripts/ci_run.py'), option, '--app', 'dify'],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8')


def test_legacy_smoke_must_not_claim_success_when_every_requested_test_skips(tmp_path):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_required.py').write_text(
        'import pytest\ndef test_required():\n    pytest.skip("synthetic missing prerequisite")\n', encoding='utf-8')
    result = legacy(tmp_path, '--smoke')
    assert result.returncode != 0, result.stdout + result.stderr


def test_legacy_regression_must_not_rerun_an_assertion_to_green(tmp_path):
    tests = tmp_path / 'examples/kb_bots'
    tests.mkdir(parents=True)
    (tests / 'test_assertion.py').write_text('''from pathlib import Path
def test_assertion():
    seen = Path("attempted")
    first = not seen.exists()
    seen.write_text("attempted")
    assert not first, "first assertion failure must remain a failing run"
''', encoding='utf-8')
    result = legacy(tmp_path, '--regression')
    assert result.returncode != 0, result.stdout + result.stderr