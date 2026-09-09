# Task 5 Report: Guide, CI Contract, Status Record, and Lifecycle Evidence

## Scope

Implemented Task 5 in the M15 worktree only.

Changed files:

- `docs/Trace 与反馈 API 指南.md`
- `tests/test_m15_docs.py`
- `README.md`
- `.github/workflows/loadtest.yml`
- `docs/AI应用全链路质量平台开发流程.md`
- `.superpowers/sdd/2026-09-08-m15-trace-feedback/task-5-report.md`

## RED

Command:

```powershell
python -m pytest tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t5-red
```

Result:

```text
6 failed
```

Expected failure evidence:

- `docs/Trace 与反馈 API 指南.md` did not exist.
- README did not link to the Trace/feedback guide.
- `.github/workflows/loadtest.yml` did not contain `m15-telemetry-contract`.
- M15 status row was still `未开始`.

One test section-boundary assertion was corrected after the first GREEN attempt because it inspected text after the README link instead of the `## Trace 与反馈 API` section. The corrected test still protects the same user-visible README contract.

## GREEN

Command:

```powershell
python -m pytest tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t5-green
```

Result:

```text
6 passed
```

Implemented behavior:

- Added a Trace/feedback guide documenting environment-only configuration, 30-day retention, no-plaintext persistence, API endpoints, CLI pruning, seven feedback categories, current read/feedback authorization limitation, PostgreSQL `NotImplementedError` boundary, and M16/M17 exclusions.
- Added README pointer to the guide and summarized M15 CLI/API environment boundaries.
- Added offline CI job `m15-telemetry-contract` with `/tmp/m15-telemetry.db` and ephemeral local values only.
- Updated the M15 process status row to `实现完成（交付进行中）` without claiming external lifecycle completion.

## Acceptance Commands

Command:

```powershell
python -m pytest tests/test_telemetry_models.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_telemetry_cli.py tests/test_reference_agent_telemetry.py tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-acceptance
```

Result:

```text
51 passed, 5 warnings
```

Final rerun after status-table/report evidence edits:

```powershell
python -m pytest tests/test_telemetry_models.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_telemetry_cli.py tests/test_reference_agent_telemetry.py tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-acceptance-final
```

Result:

```text
51 passed, 5 warnings
```

Command:

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-full
```

Result:

```text
383 passed, 4 deselected, 177 warnings
```

Command:

```powershell
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-ui
```

Result:

```text
4 passed, 383 deselected, 3 warnings
```

Command:

```powershell
python -m compileall -q llmtest qe_platform reference_agent tests
```

Result: exit code `0`.

Command:

```powershell
docker compose config --quiet
```

Result: exit code `0`.

Command:

```powershell
git diff --check
```

Result: exit code `0`; Git printed line-ending warnings for touched text files only.

## Status-Table Evidence

`docs/AI应用全链路质量平台开发流程.md` row 15 now records:

- Status: `实现完成（交付进行中）`.
- Implemented modules: `qe_platform/telemetry`, `qe_platform/storage`, `qe_platform/feedback`, `reference_agent/app.py`.
- New Task 5 artifacts: `docs/Trace 与反馈 API 指南.md`, `tests/test_m15_docs.py`, and CI `M15 telemetry contract`.
- Exact local acceptance commands/results.
- Pending lifecycle gaps: Push, Pull Request, GitHub Actions, code review, merge, Release, deployment, and issue tracking.
- Release condition: not satisfied yet.

## Manual Inspection

I inspected the final diff for the requested files. The guide uses placeholders and environment variables for secrets, contains no command-line token/API-key examples, keeps the platform and Reference Agent database boundary separate, documents the current read/feedback authorization limitation, and avoids adding new FastGPT acceptance scope.

## Self-Review

- Scope stayed inside the M15 worktree.
- Tests were added before documentation/config implementation and watched fail.
- CI job runs only offline test files from Tasks 1-5 and uses temporary local values.
- Status table does not claim Push, PR, Actions, review, merge, Release, deployment, or issue tracking.
- No production API behavior was changed in Task 5.

## Remaining Lifecycle Gaps

Pending by instruction and not claimed here:

- Push to GitHub.
- Pull Request.
- GitHub Actions.
- Code review.
- Merge to `master`.
- Release.
- Deployment.
- Issue tracking closeout.

## Commit

Required subject:

```text
docs: record milestone 15 telemetry acceptance
```
