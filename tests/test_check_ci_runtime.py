"""The project's default interpreter must not override a CI-selected runtime."""
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename', ['ci.yml', 'loadtest.yml', 'ui.yml', 'container.yml'])
def test_uv_workflows_use_the_setup_python_interpreter(filename):
    workflow = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text(encoding='utf-8'))
    assert workflow.get('env', {}).get('UV_PYTHON') == 'python', (
        'uv must resolve the setup-python PATH interpreter explicitly; .python-version is the developer default')
    for job in workflow['jobs'].values():
        steps = job['steps']
        if any('uv sync' in str(step.get('run', '')) or 'uv run' in str(step.get('run', '')) for step in steps):
            assert any(step.get('uses', '').startswith('actions/setup-python@') for step in steps), (
                'a job using uv needs an explicit setup-python runtime')