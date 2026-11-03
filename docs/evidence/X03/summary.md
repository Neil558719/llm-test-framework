# X03-A local tool evidence — Issue #85

Current local acceptance: corrected immutable `85acc66` passed all1346selected/
executed nodes with11explicit independent-environment exclusions. XML has no
failure/error/unexpected skip;373working hashes match pre/post. The check runner
verifies the existing eight runtime assets; the calibration manifest separately
binds dataset/rubric bytes, and the373file freeze includes the new corpus/tooling.
The runtime package and prior installed-consumer lineage stay unchanged. Earlier
counts and pending wording below describe their historical checkpoints. Current-head
remote CI, merge and engineering release are still separate pending stages.

Base: `1093229d2ca3cb3c3e0ab19c7e4eca55e3920d5a`, isolated
`codex/x03-judge-calibration`. This checkpoint implements repository tools and
60 synthetic silver fixtures. Independent review, root/full, current-SHA CI,
merge and release are separate pending stages. No production evaluator, provider
adapter, price table, TTL, dependency lock or runtime defaults were changed.
The initial clean freeze `34adff1` received main's independent CLI review. Its two
Important findings are corrected below and await a narrow recheck; it is not the
final accepted freeze merely because its original 53 tests passed.
Main subsequently accepted the narrow review fixes and ran the first full on
`d5de8d8`: 1340 passed, 6 path-length failures and 11 reasoned exclusions. The
latest filename correction below awaits main's narrow recheck and another full;
the failed first full is retained and is never described as successful acceptance.

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
| `main-review-red` | 3 failed / 0.91 s, exit 1 | Two existing run-contract tests and new repeated-exploration test reproduce main's two findings |
| `review-fixed-focused` | 54 passed / 1.48 s, exit 0 | Revised final X03 after the two minimal review fixes |
| `cli-consumer-v3` and `consumer-v3` | 9 command paths matched expected exits | Revised CLI consumers, including two explicit exploratory reports and unavailable run exit 2 |
| `static-ruff-red` | 3 diagnostics, exit 1 | Assigned lambdas in statistics, builder and fake-transport test |
| `static-mypy-red` | 16 diagnostics, exit 1 | Includes three dependency-discovery failures; not sixteen runtime/product defects |
| `static-ruff-fixed` | All checks passed, exit 0 | Same eight new Python files, no rule suppression |
| `static-mypy-fixed` | No issues in eight files, exit 0 | `--check-untyped-defs`, explicit package bases and actual A dependency interpreter |
| `static-fixed-focused` | 54 passed / 1.59 s, exit 0 | Final runtime contracts after the static corrections |
| `cli-consumer-v4` and `consumer-v4` | 9 command paths matched expected exits | Final-source consumers after the static corrections; 0 physical model requests |
| `windows-path-red/execution.xml` | Main full: 1340 passed / 6 failed, 11 excluded | Exact copy of actual d5de8d8 full XML; not a new implementation-agent full run |
| `windows-path-six` | 6 passed / 0.55 s, exit 0 | Exact original failed nodes, unchanged temporary-directory configuration |
| `windows-path-focused` | 54 passed / 1.56 s, exit 0 | All calibration contracts after the filename correction |
| `windows-path-ruff` and `windows-path-mypy` | Passed on 2 changed Python files, exit 0 | Same rules and untyped-body checking; remaining six files unchanged |

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
Those V2 results describe the initial freeze, not acceptance of the corrected
CLI contract: its expected zero exit for an unavailable run was incorrect. V3
changes that expectation to 2 and additionally exercises a second explicit
exploratory evaluation. The revised 54-node focused and V3 consumer runs both have
unchanged before/after working hashes. The older 172-node suite was not rerun;
neither it nor the overlapping focused suites are added to create a new total.

The real implementation-window REDs are distinct from the historical X01 REDs.
No-positive numeric F1 fitting previously preferred a false-positive solution
because undefined F1 sorted below zero; it now requires evaluable examples of both
classes. A violated input/output bound now records `strict_cap_valid=false` and
refuses every later send, even if the aggregate budget still has space. The tests
retain the original inputs; no threshold or token cap was relaxed.

## Saved CLI consumer, not Judge efficacy

`consumer-v4/inventory.json` binds nine command records and every generated file.
V1/V2/V3 are retained as historical fixture-consumer evidence; these directories are
separate artificial test runs, not repeated unseen real-Judge holdout evaluations.
The explicit model identity is `FABRICATED-OFFLINE-CLI-FIXTURE-NOT-A-JUDGE`.
Scores follow an arbitrary repeating pattern, not an actual model response.
Artifacts include a 60-row blind package, frozen policy, calibration report,
holdout report, exclusive consumption receipt, completion trace, exploratory
report and default live `not-run` JSON. Repeated normal holdout evaluation really
returned exit 2. An exploratory first evaluation also consumes holdout freshness;
a crash after reservation never restores unseen status.

Main's independent ordinary CLI review saved source-stable evidence in
`work/ci-m0-resume/x03-a-main-cli-review.json`: (I1) unavailable `run` wrote
`status=not-run` but returned 0; (I2) first holdout and first explicit exploratory
report succeeded, but the second exploratory report was already written when
identical report content collided with its append-only completion filename.
The new local REDs reproduce both before implementation changes. The minimum
I1 fix retains the not-run JSON and returns 2, including optional-budget modes.
The I2 fix adds a per-evaluation UUID to each report and its completion binding,
so distinct legitimate exploratory evaluations produce distinct append-only
completions. Their status remains exploratory; the first-use receipt is unchanged.
The regression checks three independent completion records/identities and exact
receipt-byte retention. No threshold, budget, silver label or split was altered.

The plan-required static checks were subsequently added for all four scripts,
the builder and three test files. Initial Ruff reported three assigned lambdas;
they became ordinary functions without changing inputs or outputs. Initial mypy
reported sixteen diagnostics: three were missing pytest caused by the cached tool
environment's dependency lookup. `--python-executable` now points to the existing
A test interpreter, with no install or shared-environment mutation. The remaining
diagnostics concerned dynamic dictionary/list inference, accepted price-input
types and optional Decimal arithmetic. Explicit JSON/container types and a
normalizing typed PriceQuote constructor preserve the original fake quote and
NaN inputs. A missing money reservation now has an explicit rejecting branch.
The same eight files pass Ruff and mypy `--check-untyped-defs`; no ignore rule,
reduced threshold or global configuration change was introduced. These saved
lint/type failures are static findings, distinct from the actual runtime REDs.
The final typed source then passed all 54 focused contracts in 1.59 seconds and
nine actual CLI consumer paths. Both snapshots recorded unchanged working hashes.
The previously passed 172 related nodes and B full were not rerun for these fixes.

The first actual main full on d5de8d8 found six FileNotFoundError failures because
completion filenames concatenated two 64-character hashes. They reached 144
characters and pushed the real Windows test paths beyond the native limit.
Before changing code, its XML was copied without modification to
`windows-path-red/execution.xml`; both original and copy have SHA256
`9e5abb05e1365ce372852e58c9df8e978ff9a0163a80e225c1ac42323d552c30`.
The original main command, pre/post 373 stable hashes, console and exit remain
under `.context/X02/A/x03-frozen-full/`. This actual full RED supplies the failure
evidence; no mirror negative or shortened temporary directory was introduced.

The minimum correction uses `<evaluation_id>.completed.json` (47 characters).
Payload evaluation_id and canonical report SHA remain unchanged; the original
64-character-hash first-use receipt remains unchanged too. The existing three-
completion regression now verifies a one-to-one ID/report-hash mapping to all
three reports, as well as independent evaluation identities and retained receipt
bytes. All six original failures then passed, followed by all 54 calibration
contracts. Ruff/mypy ran only on the two changed Python files and passed. No
remaining Python file, budget, label, split, OS setting or test temp path changed.
The earlier nine-CLI/V4 and B-common-tool outputs remain historical evidence;
those consumers, the eight-file static checks and B full were not rerun here.

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

Main independently reviewed the filename fix and stronger ID/report-hash mapping;
no unresolved findings remain. Replacement immutable full1346passed/11explicit
exclusions with373stable hashes; original1340passed/6failed XML remains unchanged.
Main full proof: parent work/ci-m0-resume/x03-a-frozen-full-verification.json.
B common-tool integration proof records eight actual CLI paths and a subsequent
controller-only zero-request assertion typo; read-only artifact verification
completed without rerunning those commands. Final54/full cover the later short
completion filename; B schema/statistics/budgets and corpus stayed unchanged.

Actual preliminary X04 command rehearsal at85acc66: smoke5passed and the two
validity demonstrations instantiate three parent nodes, all passed; command
elapsed14.64s in the existing local environment, not a production latency result.
No source edits, real model calls or real service-health claim. CI/merge/release
remain pending at this documentation checkpoint.
Human annotations, real Judge effects, IdP/provider/persistent environment and B
external delivery remain unverified. The interrupted complete B08 security audit
remains incomplete and was not resumed. Interview exercise and mastery are pending.