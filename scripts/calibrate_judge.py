"""Offline silver-label calibration. No provider adapter or implicit network calls."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.calibration_data import (blind_package, canonical, digest, load_corpus,
                                      load_predictions, read_json, write_new)
from scripts.calibration_statistics import binary_metrics, confusion_counts, group_intervals
from scripts.calibration_budget import BudgetLedger, PriceQuote


def _select(rows, split):
    return [row for row in rows if row['split'] == split]


def _prediction(item, direction, threshold):
    if item['status'] != 'evaluated':
        return None
    if direction == 'label':
        if item.get('label') is None:
            raise ValueError('label policy requires discrete labels, not confidence')
        return item['label']
    if item.get('score') is None:
        raise ValueError('numeric policy requires a score for each evaluated record')
    return int(item['score'] >= threshold if direction == 'ge' else item['score'] <= threshold)


def freeze_policy(manifest_path, predictions_path, output, direction='ge'):
    manifest, rows = load_corpus(manifest_path)
    selected = _select(rows, 'calibration')
    predictions, indexed = load_predictions(predictions_path, manifest, selected)
    if direction not in ('ge', 'le', 'label'):
        raise ValueError('unknown score direction')
    if not any(p['status'] == 'evaluated' for p in indexed.values()):
        raise ValueError('no evaluated calibration predictions; cannot fit a policy')
    if direction == 'label':
        threshold = None
        for item in indexed.values():
            _prediction(item, direction, None)
    else:
        if {r['expected_label'] for r in selected if indexed[r['sample_id']]['status'] == 'evaluated'} != {0, 1}:
            raise ValueError('numeric F1 fitting requires evaluable calibration examples of both classes')
        scores = sorted({p['score'] for p in indexed.values() if p['status'] == 'evaluated' and p.get('score') is not None})
        # Fixed candidate rule; endpoints and score midpoints use calibration only.
        candidates = sorted(set([0., 1.] + scores + [(a + b) / 2 for a, b in zip(scores, scores[1:])]))
        def objective(value):
            metrics = binary_metrics(confusion_counts([r['expected_label'] for r in selected],
                [_prediction(indexed[r['sample_id']], direction, value) for r in selected]))
            return (metrics['f1'] if metrics['f1'] is not None else -1,
                    metrics['recall'] if metrics['recall'] is not None else -1, -value)
        threshold = max(candidates, key=objective)
    policy = dict(schema_version='calibration-policy-v1', corpus_id=manifest['corpus_id'],
                  data_sha256=manifest['data_sha256'], rubric_sha256=manifest['rubric_sha256'],
                  model=predictions['model'], prompt_sha256=predictions['prompt_sha256'],
                  calibration_predictions_sha256=digest(Path(predictions_path).read_bytes()),
                  direction=direction, threshold=threshold, fit_split='calibration',
                  selection='max F1, then recall, then smaller threshold; no holdout tuning',
                  calibration_sample_ids=sorted(r['sample_id'] for r in selected),
                  human_verified=False, label_origin='silver')
    write_new(output, policy)
    return policy


def evaluate_report(manifest_path, predictions_path, policy_path, output, *, split='holdout',
                    state_dir=None, exploratory=False, replicates=1000):
    manifest, rows = load_corpus(manifest_path)
    if split not in ('calibration', 'holdout'):
        raise ValueError('invalid report split')
    selected = _select(rows, split)
    predictions, indexed = load_predictions(predictions_path, manifest, selected)
    policy = read_json(policy_path)
    if policy.get('schema_version') != 'calibration-policy-v1' or policy.get('fit_split') != 'calibration':
        raise ValueError('policy must be frozen from calibration')
    for key in ('corpus_id', 'data_sha256', 'rubric_sha256'):
        if policy.get(key) != manifest[key]:
            raise ValueError('policy binding mismatch: ' + key)
    for key in ('model', 'prompt_sha256'):
        if policy.get(key) != predictions[key]:
            raise ValueError('prediction identity differs from frozen policy: ' + key)
    if policy.get('calibration_sample_ids') != sorted(r['sample_id'] for r in _select(rows, 'calibration')):
        raise ValueError('policy calibration inventory mismatch')
    direction, threshold = policy.get('direction'), policy.get('threshold')
    if direction not in ('ge', 'le', 'label') or (direction == 'label' and threshold is not None):
        raise ValueError('invalid policy direction')
    if direction != 'label' and (type(threshold) not in (int, float) or not 0 <= threshold <= 1):
        raise ValueError('invalid threshold')
    if Path(output).exists():
        raise FileExistsError('report output already exists')
    # Content-based key deliberately excludes policy/model: refitting cannot reset first use.
    holdout_key = digest(canonical(sorted(_select(rows, 'holdout'), key=lambda r: r['sample_id'])))
    receipt = None
    if split == 'holdout':
        if state_dir is None:
            raise ValueError('holdout requires a persistent consumption state directory')
        receipt = Path(state_dir) / (holdout_key + '.json')
        trace = dict(schema_version='calibration-consumption-v1', holdout_sha256=holdout_key,
                     policy_sha256=digest(Path(policy_path).read_bytes()),
                     predictions_sha256=digest(Path(predictions_path).read_bytes()),
                     first_use_status='exploratory' if exploratory else 'first_use',
                     evaluation_started=True, evaluation_completed=False)
        try:
            write_new(receipt, trace)  # Atomic exclusive creation BEFORE computing any metrics.
        except FileExistsError:
            if not exploratory:
                raise ValueError('holdout already consumed; explicitly mark exploratory reevaluation')
        # An exploratory first pass consumes freshness too. Receipts are never rewritten.
    judged = [dict(group_id=r['group_id'], stratum=r['stratum'], expected=r['expected_label'],
                   predicted=_prediction(indexed[r['sample_id']], direction, threshold)) for r in selected]
    counts = confusion_counts([r['expected'] for r in judged], [r['predicted'] for r in judged])
    strata = {}
    for stratum in sorted({r['stratum'] for r in judged}):
        subset = [r for r in judged if r['stratum'] == stratum]
        c = confusion_counts([r['expected'] for r in subset], [r['predicted'] for r in subset])
        strata[stratum] = dict(counts=c, metrics=binary_metrics(c))
    statuses = Counter(indexed[r['sample_id']]['status'] for r in selected)
    report = dict(schema_version='calibration-report-v1', evaluation_id=uuid4().hex,
                  corpus_id=manifest['corpus_id'], split=split,
                  status='exploratory' if exploratory else ('holdout_first_use' if split == 'holdout' else 'calibration'),
                  label_origin='silver', human_verified=False, tool_ready=True,
                  interpretation='Agreement with AI-authored synthetic silver labels; not human gold accuracy or real Judge efficacy.',
                  counts=dict(total=len(selected), labeled=len(selected), evaluable=statuses['evaluated'],
                              abstain=statuses['abstain'], error=statuses['error'], not_executed=statuses['not_executed']),
                  confusion=counts, metrics=binary_metrics(counts), strata=strata,
                  uncertainty=group_intervals(judged, replicates=replicates, seed=manifest['seed']),
                  bindings={key: policy[key] for key in ('model', 'prompt_sha256', 'data_sha256', 'rubric_sha256', 'direction', 'threshold')},
                  policy_sha256=digest(Path(policy_path).read_bytes()),
                  predictions_sha256=digest(Path(predictions_path).read_bytes()),
                  holdout_sha256=holdout_key, consumption_receipt=None if receipt is None else str(receipt),
                  live=dict(status='not-run', physical_requests=0, actual_tokens=None, actual_cost=None))
    write_new(output, report)
    if receipt is not None:
        # Separate append-only completion record; a crash still leaves consumption recorded.
        completion = Path(state_dir) / (report['evaluation_id'] + '.completed.json')
        write_new(completion, dict(evaluation_id=report['evaluation_id'],
                                   report_sha256=digest(canonical(report)), evaluation_completed=True))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'prepare-annotations', 'freeze', 'report', 'run'):
        command = sub.add_parser(name)
        command.add_argument('--manifest', required=True)
        if name in ('prepare-annotations', 'freeze', 'report', 'run'):
            command.add_argument('--output', required=True)
        if name in ('freeze', 'report'):
            command.add_argument('--predictions', required=True)
        if name == 'freeze':
            command.add_argument('--direction', choices=('ge', 'le', 'label'), default='ge')
        if name == 'report':
            command.add_argument('--policy', required=True)
            command.add_argument('--split', choices=('calibration', 'holdout'), default='holdout')
            command.add_argument('--state-dir')
            command.add_argument('--exploratory', action='store_true')
        if name == 'run':
            command.add_argument('--max-requests', type=int, default=0)
            command.add_argument('--max-tokens', type=int, default=0)
            command.add_argument('--max-cost', help='Money cap in the quote currency; no implicit exchange rate')
            command.add_argument('--price-quote', help='JSON with explicit input/output per-million rates, source, currency and pricing_version')
    args = parser.parse_args(argv)
    try:
        manifest, rows = load_corpus(args.manifest)
        if args.command == 'validate':
            result = dict(valid=True, counts=manifest['counts'], human_verified=False)
        elif args.command == 'prepare-annotations':
            result = blind_package(manifest, rows)
            write_new(args.output, result)
        elif args.command == 'freeze':
            result = freeze_policy(args.manifest, args.predictions, args.output, args.direction)
        elif args.command == 'report':
            result = evaluate_report(args.manifest, args.predictions, args.policy, args.output,
                                     split=args.split, state_dir=args.state_dir, exploratory=args.exploratory)
        else:
            quote = None
            if args.price_quote:
                values = read_json(args.price_quote)
                quote = PriceQuote(*(values[key] for key in ('input_per_million', 'output_per_million', 'source', 'currency', 'pricing_version')))
            budget = BudgetLedger(args.max_requests, args.max_tokens, args.max_cost, quote)
            blockers = ['authorized_provider_adapter', 'reliable_provider_tokenizer']
            if budget.max_cost is not None and quote is None:
                blockers.append('explicit_price_quote_for_money_cap')
            result = dict(status='not-run', reason='No authorized provider adapter or reliable provider tokenizer; offline tool only.',
                          physical_requests=0, actual_tokens=None, actual_cost=None,
                          max_requests=args.max_requests, max_tokens=args.max_tokens,
                          max_cost=None if budget.max_cost is None else str(budget.max_cost),
                          configured_price=None if quote is None else dict(input_per_million=str(quote.input_per_million),
                              output_per_million=str(quote.output_per_million), source=quote.source,
                              currency=quote.currency, pricing_version=quote.pricing_version),
                          budget_blockers=blockers, human_verified=False)
            write_new(args.output, result)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if args.command == 'run' else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('calibration error: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())