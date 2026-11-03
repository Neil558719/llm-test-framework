"""Offline tool consumer contracts; all prediction files below are fabricated fixtures."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.calibrate_judge import evaluate_report, freeze_policy, main
from scripts.calibration_data import blind_package, canonical, digest, load_corpus, read_json

CORPUS = Path(__file__).resolve().parents[1] / 'benchmarks/judge_calibration'


def test_corpus_rebuild_matches_raw_bytes_and_refuses_existing_output(tmp_path):
    target = tmp_path / 'rebuilt'
    command = [sys.executable, str(CORPUS / 'build_corpus.py'), '--outdir', str(target)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    expected = {name: (CORPUS / name).read_bytes() for name in ('dataset.jsonl', 'manifest.json', 'rubric.md')}
    assert all((target / name).read_bytes() == data for name, data in expected.items())
    second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    assert second.returncode != 0
    assert all((target / name).read_bytes() == data for name, data in expected.items())


@pytest.fixture
def corpus(tmp_path):
    target = tmp_path / 'corpus'
    shutil.copytree(CORPUS, target)
    return target / 'manifest.json'


def rebind(path, rows=None, manifest=None):
    manifest = read_json(path) if manifest is None else manifest
    if rows is not None:
        data = ''.join(json.dumps(r) + '\n' for r in rows).encode()
        (path.parent / manifest['data_file']).write_bytes(data)
        manifest['data_sha256'] = digest(data)
    path.write_text(json.dumps(manifest), encoding='utf-8')


def predictions(path, split, output, transform=None):
    manifest, rows = load_corpus(path)
    items = [dict(sample_id=r['sample_id'], status='evaluated', label=r['expected_label'],
                  score=.9 if r['expected_label'] else .1) for r in rows if r['split'] == split]
    if transform:
        transform(items)
    value = dict(schema_version='calibration-predictions-v1', corpus_id=manifest['corpus_id'],
                 data_sha256=manifest['data_sha256'], rubric_sha256=manifest['rubric_sha256'],
                 model='FAKE-OFFLINE-TRANSPORT-NOT-A-JUDGE', prompt_sha256=digest(b'synthetic prompt'),
                 predictions=items)
    output.write_text(json.dumps(value), encoding='utf-8')
    return output


def frozen(corpus, tmp_path, direction='ge'):
    cal = predictions(corpus, 'calibration', tmp_path / 'cal.json')
    policy = tmp_path / 'policy.json'
    freeze_policy(corpus, cal, policy, direction=direction)
    return policy


def test_committed_corpus_contract_and_public_diagnostic_is_calibration_only(corpus):
    manifest, rows = load_corpus(corpus)
    assert manifest['counts']['samples'] == 60 and manifest['counts']['groups'] == 30
    assert manifest['counts']['splits'] == {'calibration': 42, 'holdout': 18}
    assert set(manifest['counts']['strata'].values()) == {10}
    for stratum, expected in zip(manifest['counts']['strata'], [4, 3, 4, 3, 4, 3]):
        assert len({r['group_id'] for r in rows if r['stratum'] == stratum and r['split'] == 'calibration'}) == expected
    diagnostic = [r for r in rows if r['group_id'] == 'A-num-01']
    assert len(diagnostic) == 2 and all(r['split'] == 'calibration' for r in diagnostic)
    assert all(r['expected_label'] == 1 for r in diagnostic)
    assert {'7 days', '9999 days'} == {r['response'].removeprefix('The return window is ').removesuffix('.') for r in diagnostic}


@pytest.mark.parametrize('mutation,match', [
    (lambda m, r: r[0].update(expected_label=True), 'invalid label'),
    (lambda m, r: r[0].update(annotator_id='person-A'), 'human provenance'),
    (lambda m, r: r[0].update(sample_id=r[1]['sample_id']), 'duplicate sample'),
    (lambda m, r: r[0].update(split='holdout' if r[1]['split'] == 'calibration' else 'calibration'), 'split leakage'),
    (lambda m, r: m['counts'].update(samples=59), 'count inventory'),
    (lambda m, r: m['provenance'].update(human_review='verified'), 'human provenance'),
    (lambda m, r: r[2].update(input=r[0]['input']), 'template crosses'),
])
def test_invalid_corpora_rejected_even_with_recomputed_hashes(corpus, mutation, match):
    manifest, rows = load_corpus(corpus)
    mutation(manifest, rows)
    rebind(corpus, rows, manifest)
    with pytest.raises(ValueError, match=match):
        load_corpus(corpus)


def test_raw_hash_mismatch_rejected_before_metrics(corpus):
    (corpus.parent / 'rubric.md').write_text('modified', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_corpus(corpus)


def test_blind_package_contains_neither_labels_predictions_nor_answer_coded_references(corpus):
    manifest, rows = load_corpus(corpus)
    package = blind_package(manifest, rows)
    assert package['human_verified'] is False and len(package['records']) == 60
    forbidden = {'expected_label', 'label_origin', 'source_reference', 'prediction', 'split', 'stratum', 'annotator_id', 'adjudication'}
    assert all(not (set(r) & forbidden) and r['annotation'] is None for r in package['records'])
    assert {r['sample_id'] for r in package['records']}.isdisjoint({r['sample_id'] for r in rows})


def test_security_manifest_consumption_needs_no_airt_import(corpus):
    manifest, rows = load_corpus(corpus)
    manifest.update(corpus_id='B-SCHEMA-FIXTURE-NOT-A-SECURITY-CORPUS', positive_label='security_violation')
    for row in rows:
        row['domain'] = 'security'
    rebind(corpus, rows, manifest)
    assert load_corpus(corpus)[0]['positive_label'] == 'security_violation'


def test_calibration_freeze_is_exclusive_and_rejects_holdout_predictions(corpus, tmp_path):
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    with pytest.raises(ValueError, match='exactly cover'):
        freeze_policy(corpus, holdout, tmp_path / 'bad.json')
    policy = frozen(corpus, tmp_path)
    before = policy.read_bytes()
    with pytest.raises(FileExistsError):
        freeze_policy(corpus, tmp_path / 'cal.json', policy)
    assert policy.read_bytes() == before


def test_holdout_consumed_before_metrics_and_repeat_requires_explicit_exploration(corpus, tmp_path):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    state = tmp_path / 'state'
    report = evaluate_report(corpus, holdout, policy, tmp_path / 'report.json', state_dir=state, replicates=20)
    receipt = Path(report['consumption_receipt'])
    before = receipt.read_bytes()
    assert report['status'] == 'holdout_first_use' and report['human_verified'] is False
    assert report['counts']['total'] == 18 and report['confusion']['total'] == 18
    assert report['live']['physical_requests'] == 0
    assert read_json(receipt)['evaluation_started'] is True
    with pytest.raises(ValueError, match='already consumed'):
        evaluate_report(corpus, holdout, policy, tmp_path / 'second.json', state_dir=state)
    result = evaluate_report(corpus, holdout, policy, tmp_path / 'exploratory.json', state_dir=state, exploratory=True, replicates=20)
    assert result['status'] == 'exploratory' and receipt.read_bytes() == before


def test_exploratory_first_use_also_consumes_holdout(corpus, tmp_path):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    state = tmp_path / 'state'
    evaluate_report(corpus, holdout, policy, tmp_path / 'explore.json', state_dir=state, exploratory=True, replicates=20)
    with pytest.raises(ValueError, match='already consumed'):
        evaluate_report(corpus, holdout, policy, tmp_path / 'unseen.json', state_dir=state)


def test_each_explicit_exploratory_report_has_an_independent_completion(corpus, tmp_path):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    state = tmp_path / 'state'
    first = evaluate_report(corpus, holdout, policy, tmp_path / 'first.json', state_dir=state, replicates=20)
    receipt = Path(first['consumption_receipt'])
    original_receipt = receipt.read_bytes()
    evaluation_ids = {first['evaluation_id']}
    reports = [first]
    for name in ('exploratory-one.json', 'exploratory-two.json'):
        output = tmp_path / name
        assert main(['report', '--manifest', str(corpus), '--predictions', str(holdout),
                     '--policy', str(policy), '--state-dir', str(state), '--output', str(output),
                     '--exploratory']) == 0
        report = read_json(output)
        assert report['status'] == 'exploratory'
        evaluation_ids.add(report['evaluation_id'])
        reports.append(report)
    assert receipt.read_bytes() == original_receipt
    assert len(list(state.glob('*.completed.json'))) == 3
    assert len(evaluation_ids) == 3
    completions = [read_json(path) for path in state.glob('*.completed.json')]
    assert {item['evaluation_id']: item['report_sha256'] for item in completions} == {
        report['evaluation_id']: digest(canonical(report)) for report in reports}


def test_changing_policy_does_not_reset_holdout_consumption(corpus, tmp_path):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    state = tmp_path / 'state'
    evaluate_report(corpus, holdout, policy, tmp_path / 'first.json', state_dir=state, replicates=20)
    changed = read_json(policy)
    changed['threshold'] = .7
    another = tmp_path / 'another-policy.json'
    another.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(ValueError, match='already consumed'):
        evaluate_report(corpus, holdout, another, tmp_path / 'second.json', state_dir=state)


def test_low_score_direction_is_explicit_and_not_confidence(corpus, tmp_path):
    def reverse(items):
        for item in items:
            item['score'] = 1 - item['score']
    cal = predictions(corpus, 'calibration', tmp_path / 'cal.json', reverse)
    policy = tmp_path / 'le-policy.json'
    freeze_policy(corpus, cal, policy, direction='le')
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json', reverse)
    report = evaluate_report(corpus, holdout, policy, tmp_path / 'le-report.json', state_dir=tmp_path / 'state', replicates=20)
    assert report['metrics']['f1'] == 1 and report['bindings']['direction'] == 'le'


def test_discrete_policy_rejects_confidence_only_outputs(corpus, tmp_path):
    cal = predictions(corpus, 'calibration', tmp_path / 'cal.json', lambda items: [item.update(label=None) for item in items])
    with pytest.raises(ValueError, match='discrete labels'):
        freeze_policy(corpus, cal, tmp_path / 'policy.json', direction='label')


def test_failure_after_consumption_cannot_restore_unseen_status(corpus, tmp_path, monkeypatch):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic statistics interruption')
    monkeypatch.setattr('scripts.calibrate_judge.group_intervals', fail)
    state = tmp_path / 'state'
    with pytest.raises(RuntimeError):
        evaluate_report(corpus, holdout, policy, tmp_path / 'failed.json', state_dir=state)
    assert len(list(state.glob('*.json'))) == 1
    with pytest.raises(ValueError, match='already consumed'):
        evaluate_report(corpus, holdout, policy, tmp_path / 'retry.json', state_dir=state)


@pytest.mark.parametrize('mutation', [
    lambda p: p.pop(), lambda p: p.append(copy.deepcopy(p[0])),
    lambda p: p[0].update(score=float('nan')), lambda p: p[0].update(label=True),
    lambda p: p[0].update(status='error'), lambda p: p[0].update(sample_id='unknown'),
])
def test_invalid_predictions_are_not_silently_dropped(corpus, tmp_path, mutation):
    cal = predictions(corpus, 'calibration', tmp_path / 'bad.json', mutation)
    with pytest.raises(ValueError):
        freeze_policy(corpus, cal, tmp_path / 'policy.json')


def test_abstain_error_and_not_executed_are_separate_from_evaluable(corpus, tmp_path):
    policy = frozen(corpus, tmp_path, direction='label')
    def modify(items):
        for item, status in zip(items, ['abstain', 'error', 'not_executed']):
            item.update(status=status, score=None, label=None)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json', modify)
    report = evaluate_report(corpus, holdout, policy, tmp_path / 'report.json', state_dir=tmp_path / 'state', replicates=20)
    assert report['counts'] == dict(total=18, labeled=18, evaluable=15, abstain=1, error=1, not_executed=1)
    assert report['confusion']['abstain'] == 3
    assert report['metrics']['coverage'] == pytest.approx(15 / 18)


def test_prediction_identity_cannot_change_after_freeze(corpus, tmp_path):
    policy = frozen(corpus, tmp_path)
    holdout = predictions(corpus, 'holdout', tmp_path / 'holdout.json')
    data = read_json(holdout)
    data['model'] = 'another-model'
    holdout.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='identity differs'):
        evaluate_report(corpus, holdout, policy, tmp_path / 'report.json', state_dir=tmp_path / 'state')


def test_numeric_fitting_cannot_prefer_false_positives_when_calibration_has_no_positives(corpus, tmp_path):
    manifest, rows = load_corpus(corpus)
    for row in rows:
        if row['split'] == 'calibration':
            row['expected_label'] = 0
    rebind(corpus, rows, manifest)
    cal = predictions(corpus, 'calibration', tmp_path / 'cal.json')
    with pytest.raises(ValueError, match='both classes'):
        freeze_policy(corpus, cal, tmp_path / 'policy.json')


def test_live_cli_default_and_explicit_budget_are_not_run_without_adapter(corpus, tmp_path, capsys):
    for suffix, options in [('default', []), ('explicit', ['--max-requests', '1', '--max-tokens', '100'])]:
        output = tmp_path / (suffix + '.json')
        assert main(['run', '--manifest', str(corpus), '--output', str(output)] + options) == 2
        result = read_json(output)
        assert result['status'] == 'not-run' and result['physical_requests'] == 0
        assert result['actual_tokens'] is None and result['actual_cost'] is None
    assert read_json(tmp_path / 'default.json')['max_requests'] == 0


def test_cli_optional_money_cap_retains_unknown_price_and_explicit_quote_identity(corpus, tmp_path, capsys):
    unknown = tmp_path / 'unknown.json'
    assert main(['run', '--manifest', str(corpus), '--output', str(unknown), '--max-cost', '.01']) == 2
    result = read_json(unknown)
    assert result['actual_cost'] is None and result['configured_price'] is None
    assert 'explicit_price_quote_for_money_cap' in result['budget_blockers']
    quote = tmp_path / 'quote.json'
    quote.write_text(json.dumps(dict(input_per_million=1, output_per_million=2,
        source='fake offline quote', currency='USD', pricing_version='fixture-v1')), encoding='utf-8')
    known = tmp_path / 'known.json'
    assert main(['run', '--manifest', str(corpus), '--output', str(known), '--max-cost', '.01', '--price-quote', str(quote)]) == 2
    result = read_json(known)
    assert result['status'] == 'not-run' and result['physical_requests'] == 0 and result['actual_cost'] is None
    assert result['configured_price']['currency'] == 'USD' and result['configured_price']['pricing_version'] == 'fixture-v1'