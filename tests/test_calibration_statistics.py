"""Deterministic statistics, without a model or a purported human annotator."""
import pytest

from scripts.calibrate_judge import binary_metrics, confusion_counts
from scripts.calibration_statistics import group_intervals, wilson_interval


def test_metrics_from_known_labels():
    counts = confusion_counts([1, 1, 0, 0], [1, 0, 1, 0])
    assert counts == {'tp': 1, 'tn': 1, 'fp': 1, 'fn': 1, 'abstain': 0, 'total': 4}
    metrics = binary_metrics(counts)
    assert metrics['precision'] == metrics['recall'] == metrics['f1'] == .5


def test_empty_denominators_are_unknown():
    metrics = binary_metrics(confusion_counts([], []))
    assert all(value is None for value in metrics.values())
    assert wilson_interval(0, 0) is None


def test_abstentions_preserve_the_total_and_are_not_correct():
    counts = confusion_counts([1, 0, 1], [None, 0, None])
    assert counts['total'] == 3 and counts['abstain'] == 2
    metrics = binary_metrics(counts)
    assert metrics['coverage'] == pytest.approx(1 / 3)
    assert metrics['precision'] is None and metrics['f1'] is None
    assert metrics['agreement'] == 1  # Conditional on the single evaluable pair.


@pytest.mark.parametrize('expected,predicted', [([True], [1]), ([1], [False]),
    ([2], [0]), ([1], [float('nan')]), ([0, 1], [0])])
def test_invalid_or_mismatched_labels_are_rejected(expected, predicted):
    with pytest.raises(ValueError):
        confusion_counts(expected, predicted)


def test_zero_f1_is_distinct_from_undefined_f1():
    assert binary_metrics(confusion_counts([1, 0], [0, 1]))['f1'] == 0
    assert binary_metrics(confusion_counts([0], [0]))['f1'] is None


def test_independent_wilson_interval_does_not_claim_perfect_certainty():
    low, high = wilson_interval(4, 4)
    assert 0 < low < 1 and high == pytest.approx(1)


def test_cluster_bootstrap_repeats_groups_not_individual_variants():
    rows = [{'group_id': group, 'stratum': 'numeric_condition_error',
             'expected': expected, 'predicted': predicted}
            for group, expected, predicted in [('a', 1, 1), ('a', 1, 0), ('b', 0, 0), ('b', 0, 1)]]
    first = group_intervals(rows, replicates=100, seed=20261103)
    assert first == group_intervals(rows, replicates=100, seed=20261103)
    assert first['groups'] == 2 and first['method'] == 'stratified_group_bootstrap'
    assert first['replicates'] == 100 and first['intervals']['f1'] is not None


def test_single_group_interval_is_not_invented():
    result = group_intervals([{'group_id': 'only', 'stratum': 'normal_citation',
        'expected': 0, 'predicted': 0}], replicates=30)
    assert result['insufficient_groups'] and all(v is None for v in result['intervals'].values())