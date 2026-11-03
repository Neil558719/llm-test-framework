# X03-A local tool evidence — Issue #85

Base: `1093229d2ca3cb3c3e0ab19c7e4eca55e3920d5a`, isolated
`codex/x03-judge-calibration`. This checkpoint implements repository tools and
60 synthetic silver fixtures. Independent review, root/full, current-SHA CI,
merge and release are separate pending stages. No production evaluator, provider
adapter, price table, TTL, dependency lock or runtime defaults were changed.

## Corpus and tool boundary

The manifest binds raw data/rubric SHA256, positive-label direction, label origin,
group/sample inventories and splits. A has 30 distinct business-intent groups,
two variants each, six strata of ten, 42 calibration and 18 holdout records.
Per-stratum calibration groups are 4/3/4/3/4/3 with seed 20261103.
The published English 14/7/9999-day diagnostic remains in `A-num-01`, calibration
only. Existing X01 English Mock failures are not repaired or rewritten here.
The prior proof `work/ci-m0-resume/x01-reviewed-final-verification.json` explicitly
retains them; the main execution ledger records their original 4 passed/2 failed.

`validate`, `prepare-annotations`, `freeze`, `report` and `run` are documented in
[the tool guide](../../calibration.md). B's shared schema is accepted without an
`airt` import. The generator writes explicit UTF-8/LF and refuses an existing
output directory; byte-rebuild tests cover all three assets. The corpus-scoped
`.gitattributes` retains LF through fresh checkouts. Human labels/adjudication do
not exist: silver/synthetic, null annotator/adjudication, human review pending,
`human_verified=false` throughout. The blind package excludes answer keys,
predictions, strata, splits and answer-coded IDs.

## Actual local sequence

All raw command/log/XML/hash records are retained under root `.context/X03/A/`.
The existing private Python 3.12.14 environment was reused read-only; environment
keys and real-provider variables were removed from child invocations. No package
installation, network, Docker or service mutation occurred.

| Evidence directory | Actual result | Interpretation |
| --- | --- | --- |
| `interface-gap` | 1 collection error, exit 2 | Missing new module only; not a business RED |
| `focused-first` | 22 passed | Initial statistics and fake physical-send budget contracts |
| `focused-workflow` | 46 passed | Initial corpus/workflow contracts |
| `single-class-red` | 1 failed, exit 1 | Fitter incorrectly accepted no-positive calibration |
| `focused-related` | 171 passed | Minimal both-class fitting guard plus related contracts |
| `bound-breach-red` | 1 failed, exit 1 | Broken token bound still allowed a subsequent physical send |
| `final-related` | 172 passed / 25.67 s, exit 0 | 51 X03 nodes plus 121 validity/check-selection nodes after both fixes |
| `final-focused` | 52 passed / 1.31 s, exit 0 | Added raw-byte rebuild/overwrite consumer |
| `cli-consumer` and `consumer-v1` | 8 command paths matched expected exits | Initial actual CLI invocation with fabricated predictions |
| `final-focused-v2` | 53 passed / 1.55 s, exit 0 | Final X03 including explicit optional CLI money cap/price quote |
| `cli-consumer-v2` and `consumer-v2` | 8 command paths matched expected exits | Final actual CLI consumers; 0 physical model requests |

The final-focused-v2 and cli-consumer-v2 runs both completed before a usage-limit
interruption; their existing session output, exit files and unchanged before/after
working-file hashes were recovered afterwards without rerunning tests. V2 adds
CLI `--max-cost` and `--price-quote`, preserves explicit currency/source/version,
and reports a missing price as a blocker while execution remains `not-run`.
The earlier final-related and CLI snapshots were stable too. Updating only this
evidence note afterwards does not constitute another test run. Related 172 and
final 53 are overlapping suites, not 225 unique passes or a final root/full result.
The 172-node related run precedes the last corpus-rebuilder and CLI-price consumers;
the final 53-node suite covers those additions. Three new test files are in both
`scripts/check-manifest.json` inventories (`files` and `core`); smoke is unchanged.

The real implementation-window REDs are distinct from the historical X01 REDs.
No-positive numeric F1 fitting previously preferred a false-positive solution
because undefined F1 sorted below zero; it now requires evaluable examples of both
classes. A violated input/output bound now records `strict_cap_valid=false` and
refuses every later send, even if the aggregate budget still has space. The tests
retain the original inputs; no threshold or token cap was relaxed.

## Saved CLI consumer, not Judge efficacy

`consumer-v2/inventory.json` binds eight command records and every generated file.
V1 is retained as historical fixture-consumer evidence; the two directories are
separate artificial test runs, not repeated unseen real-Judge holdout evaluations.
The explicit model identity is `FABRICATED-OFFLINE-CLI-FIXTURE-NOT-A-JUDGE`.
Scores follow an arbitrary repeating pattern, not an actual model response.
Artifacts include a 60-row blind package, frozen policy, calibration report,
holdout report, exclusive consumption receipt, completion trace, exploratory
report and default live `not-run` JSON. Repeated normal holdout evaluation really
returned exit 2. An exploratory first evaluation also consumes holdout freshness;
a crash after reservation never restores unseen status.

For this fabricated fixture only, calibration contains 42 labeled, 40 evaluable,
1 abstain and 1 error (TP14/TN0/FP26/FN0, F1≈0.5185); holdout contains 18 labeled,
16 evaluable, 1 abstain and 1 error (TP5/TN0/FP11/FN0, F1≈0.4762). These numbers
exercise the report and establish no real Judge quality. Holdout has nine groups,
including strata with one group: intervals are explicitly null/insufficient,
rather than a falsely precise confidence claim. Conditional metrics and coverage
are both present. Null denominators and undefined bootstrap replicas remain visible.

Request/token/optional money budgets are verified with injected fake transports:
every physical send/retry reserves input plus bounded output before dispatch;
unknown/invalid usage and failures keep reservations; hidden SDK retries are zero.
Missing prices yield null cost; a configured money cap requires explicit prices,
currency, source and version. The CLI always reports live `not-run`, default
max_requests=0, actual tokens/cost unknown. No authorized provider/tokenizer exists.
This is `tool_ready` engineering evidence, not `human_verified` or an efficacy gate.

## Predecessor and remaining stages

Main confirmed X02-A engineering delivery: PR83 merged `1093229`, same tree as
reviewed `7d086f`; merged1292 passed/11 reasoned exclusions, 259 stable fresh hashes,
21 CI checks passed. Actual 21-context protection and failed PR84 BLOCKED behavior
were verified. Engineering prerelease `x02-ci-20261103` was downloaded and matched
its two JSON assets and tag. It does not replace the dev8 runtime wheel.

X03 independent static review/full/CI/merge/release remain pending at this handoff.
Human annotations, real Judge effects, IdP/provider/persistent environment and B
external delivery remain unverified. The interrupted complete B08 security audit
remains incomplete and was not resumed. Interview exercise and mastery are pending.