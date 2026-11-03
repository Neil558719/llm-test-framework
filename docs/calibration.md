# Offline Judge calibration

Run `python scripts/calibrate_judge.py validate --manifest benchmarks/judge_calibration/manifest.json`
from this checkout. The script also accepts the B security corpus using the shared
`judge-calibration-v1` schema; it imports no `airt` code. These scripts and fixtures
are repository tools, not a new wheel API or a replacement for the existing Judge.

The A corpus contains 60 AI-authored synthetic silver records in 30 intent groups.
Each group has two variants. Six coverage strata contain ten records each; group
splits contain 42 calibration and 18 holdout records, seed 20261103. Split membership
is frozen in the manifest before fitting. Each stratum uses different business
intents; changing only a resource ID or number does not create an independent group.
The numeric English 14/7/9999-day diagnostic is already public and is calibration
only. Its known Mock failures remain historical evidence, not new calibration success.

`quality_error=1` means a wrong, unsupported or incomplete required answer, including
denying a synthetic tool action that its trace records as completed. The B positive
label is `security_violation=1`; an incorrect number alone is not such a violation.
All tools and references in the corpus are fabricated. A no-factual-claim control
is negative for quality error; the production hallucination evaluator may abstain.

`python benchmarks/judge_calibration/build_corpus.py --outdir <new-directory>`
rebuilds the three assets with explicit UTF-8/LF bytes and refuses an existing
output directory. The scoped `.gitattributes` also preserves LF in fresh checkouts;
neither the generator nor report commands overwrite an existing corpus or report.

Use `prepare-annotations --manifest ... --output blind.json` to export an annotation
package. It excludes silver labels, stratum, split, coded references and predictions.
Opaque IDs remove answer-coded group prefixes. IDs are the first 24 hex characters
of SHA256(`annotation:` + original ID), so completed annotations can later be joined
privately without publishing the answer key. Give independent annotators only the
package and rubric. No human annotation import/adjudication is claimed in v1:
`annotator_id` and `adjudication` are null; `human_verified` stays false.

Supply a separate prediction JSON for each selected split:

```json
{
  "schema_version": "calibration-predictions-v1",
  "corpus_id": "A-quality-silver-v1",
  "data_sha256": "<manifest data hash>",
  "rubric_sha256": "<manifest rubric hash>",
  "model": "<explicit model/version or fabricated fixture identity>",
  "prompt_sha256": "<64 lowercase hex characters>",
  "predictions": [
    {"sample_id": "<id>", "status": "evaluated", "score": 0.7, "label": null}
  ]
}
```

The list must exactly cover the chosen split. `score` is an explicitly chosen
continuous decision variable in [0,1], not automatically Judge confidence. Use
`--direction ge` when a higher score means the positive label, `le` for the reverse,
or `label` for discrete binary predictions. The latter requires exact integer labels
and performs no threshold search. Non-evaluated statuses are `abstain`, `error` or
`not_executed`; their score and label must both be null. NaN, Boolean labels,
duplicates, missing IDs, hash changes and forged human provenance are rejected.

```text
python scripts/calibrate_judge.py freeze --manifest <manifest> --predictions cal.json --direction ge --output policy.json
python scripts/calibrate_judge.py report --manifest <manifest> --predictions cal.json --policy policy.json --split calibration --output calibration.json
python scripts/calibrate_judge.py report --manifest <manifest> --predictions holdout.json --policy policy.json --state-dir <persistent-state> --output holdout.json
```

Numeric fitting requires both classes among evaluable calibration examples. It
chooses maximum F1, then recall, then the smaller threshold on a fixed candidate
grid of calibration scores, midpoints and [0,1] endpoints. Frozen policies bind
the model, prompt, data, rubric, calibration predictions and sample inventory.
Outputs are created exclusively; there is no overwrite option.

Holdout consumption is written exclusively before metrics are calculated, keyed
by holdout content rather than policy/model. A failed report still consumes it.
Repeating evaluation requires `--exploratory` and a distinct output. Even an initial
exploratory evaluation consumes freshness. Completion is a separate append-only
record; the start receipt is never rewritten. Each report has its own `evaluation_id`,
so repeated explicit exploratory evaluations append independent completion records.
Completion filenames use that 32-character ID; report hashes remain inside the
record. This keeps completion paths shorter than the unchanged first-use receipt,
avoiding the former concatenated-hash filename's Windows path-length failure.
Use one durable authoritative state
directory and retain it with the corpus. This local accidental-reuse guard is not
tamper-proof: deleting state, choosing another state directory or editing files
requires operator discipline and does not establish fresh unseen evaluation.

Reports distinguish total/labeled/evaluable/abstain/error/not-executed counts and
preserve all records. Confusion counts combine non-evaluated rows under `abstain`;
the status inventory retains their separate causes. Precision/recall/F1/agreement
condition on evaluable rows; coverage exposes exclusions. Undefined denominators
are null, not zero or perfect agreement. F1 is zero when its denominator exists but
its numerator is zero. Intervals resample whole groups within strata with a fixed
seed. When any stratum has fewer than two groups, intervals are null with an
explicit insufficient-groups flag. Undefined bootstrap replicates are counted and
never silently discarded to tighten an interval. Wilson is available only as an
independent-binomial helper, not applied to correlated variants. These small
synthetic groups do not establish population independence or real Judge efficacy.

`run --manifest ... --output live.json` defaults to zero requests and always records
`not-run`: no provider adapter, reliable provider tokenizer or paid authorization
is supplied. It preserves the JSON report and returns exit code 2 so shell callers
cannot treat a request that did not run as successful execution. Offline validate,
annotation, freeze and report commands return 0 on success. Explicit nonzero CLI
budgets do not enable dispatch. The separate
`BudgetLedger` is tested only with injected fake transports. It serializes sends,
reserves full input plus output allowance before every physical send/retry,
disables hidden SDK retries, and retains reservations on unknown/invalid usage or
transport failure. It reconciles only known usage. A broken bound is recorded and
blocks later sends; it cannot be relabeled a successful strict cap. Unknown price
means null cost. A money cap requires explicit input/output prices, source,
currency and pricing version. CLI `--max-cost` accepts a cap; optional `--price-quote`
loads JSON fields `input_per_million`, `output_per_million`, `source`, `currency`
and `pricing_version`. A missing quote is an explicit blocker, never a zero price.
Supplying a quote still leaves live execution `not-run`. Reliable bounds are caller obligations; this ledger
is not itself a provider tokenizer. Production budgets/defaults are unchanged.