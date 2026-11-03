"""Child pytest observer used only by scripts/check.py (no reruns)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.check import exclusion, validate_inventory, write_json

_settings = json.loads(Path(os.environ['CHECK_SETTINGS_FILE']).read_text(encoding='utf-8'))
_evidence: dict[str, Any] = {'selected': [], 'excluded': [], 'events': [], 'errors': []}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    try:
        validate_inventory([item.nodeid for item in items], _settings['manifest'])
    except ValueError as error:
        _evidence['errors'].append(str(error))
        raise pytest.UsageError(str(error)) from error
    selected, excluded = [], []
    for item in items:
        reason = exclusion(item.nodeid, _settings['manifest'], _settings['tier'])
        if reason:
            excluded.append(item)
            _evidence['excluded'].append({'nodeid': item.nodeid, 'reason': reason})
        else:
            selected.append(item)
    _evidence['selected'] = [item.nodeid for item in selected]
    items[:] = selected
    config.hook.pytest_deselected(items=excluded)


def pytest_collectreport(report):
    if report.failed or report.skipped:
        _evidence['errors'].append('collection ' + report.outcome + ': ' + report.nodeid)


def pytest_runtest_logreport(report):
    _evidence['events'].append({'nodeid': report.nodeid, 'phase': report.when,
        'outcome': report.outcome, 'wasxfail': hasattr(report, 'wasxfail')})


def pytest_sessionfinish(session, exitstatus):
    write_json(Path(_settings['output']), _evidence)