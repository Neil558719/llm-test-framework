"""Binary silver-label agreement; variants are resampled together by group."""
import math
import random
from collections import defaultdict
from statistics import NormalDist


def _binary(value):
    return type(value) is int and value in (0, 1)


def confusion_counts(expected, predicted):
    expected, predicted = list(expected), list(predicted)
    if len(expected) != len(predicted):
        raise ValueError('label sequences have different lengths')
    counts = dict(tp=0, tn=0, fp=0, fn=0, abstain=0, total=len(expected))
    for actual, guess in zip(expected, predicted):
        if not _binary(actual) or (guess is not None and not _binary(guess)):
            raise ValueError('labels must be exact binary integers; prediction may be null')
        key = 'abstain' if guess is None else (
            'tp' if actual == guess == 1 else 'tn' if actual == guess == 0
            else 'fp' if guess == 1 else 'fn')
        counts[key] += 1
    return counts


def binary_metrics(counts):
    keys = ('tp', 'tn', 'fp', 'fn', 'abstain', 'total')
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in keys):
        raise ValueError('counts must be nonnegative integers')
    tp, tn, fp, fn, abstain, total = (counts[k] for k in keys)
    if tp + tn + fp + fn + abstain != total:
        raise ValueError('counts do not sum to total')
    divide = lambda a, b: a / b if b else None
    return dict(precision=divide(tp, tp + fp), recall=divide(tp, tp + fn),
                f1=divide(2 * tp, 2 * tp + fp + fn),
                agreement=divide(tp + tn, total - abstain),
                coverage=divide(total - abstain, total))


def wilson_interval(successes, total, confidence=.95):
    if type(total) is not int or type(successes) is not int or not 0 <= successes <= total:
        raise ValueError('invalid binomial counts')
    if not 0 < confidence < 1:
        raise ValueError('confidence must be between zero and one')
    if total == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p, z2 = successes / total, z * z
    denominator = 1 + z2 / total
    middle = (p + z2 / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denominator
    return [max(0., middle - half), min(1., middle + half)]


def group_intervals(rows, replicates=1000, seed=20261103):
    if type(replicates) is not int or replicates < 2:
        raise ValueError('at least two bootstrap replicates required')
    groups, strata = {}, defaultdict(list)
    for row in rows:
        group, stratum = row['group_id'], row['stratum']
        if group in groups and groups[group][0]['stratum'] != stratum:
            raise ValueError('group crosses strata')
        groups.setdefault(group, []).append(row)
    for group, members in sorted(groups.items()):
        confusion_counts([x['expected'] for x in members], [x['predicted'] for x in members])
        strata[members[0]['stratum']].append(group)
    keys = tuple(binary_metrics(confusion_counts([], [])))
    result = dict(method='stratified_group_bootstrap', groups=len(groups),
                  replicates=replicates, seed=seed, confidence=.95,
                  insufficient_groups=not strata or any(len(g) < 2 for g in strata.values()),
                  intervals={k: None for k in keys}, defined_replicates={k: 0 for k in keys})
    if result['insufficient_groups']:
        return result
    rng, values = random.Random(seed), {k: [] for k in keys}
    for _ in range(replicates):
        sampled = []
        for stratum in sorted(strata):
            choices = strata[stratum]
            for group in rng.choices(choices, k=len(choices)):
                sampled.extend(groups[group])
        metrics = binary_metrics(confusion_counts([x['expected'] for x in sampled],
                                                  [x['predicted'] for x in sampled]))
        for key, value in metrics.items():
            if value is not None:
                values[key].append(value)
    for key, samples in values.items():
        result['defined_replicates'][key] = len(samples)
        # Do not silently discard undefined resamples to narrow an interval.
        if len(samples) == replicates:
            samples.sort()
            result['intervals'][key] = [samples[int(.025 * (replicates - 1))],
                                        samples[math.ceil(.975 * (replicates - 1))]]
    return result