# Installed wheel acceptance follow-up (Issue #65)

Base: merged master `3bfc43abc04053092cf90a8c44fd602054c3b2f0`, identical code tree to reviewed PR #62 head `4d8ff42`. That head passed GitHub's offline, container, UI and load checks. Merged master explicitly configured for mock passed **563 tests, 7 deselected, 2 upstream warnings**. The exclusions are UI and Windows Task Scheduler/watcher system integration. An earlier wrong-mode invocation failed four missing-SDK cases; its log remains preserved and no real requests were made.

## Failure and root cause

`uv build --wheel --offline` produced a wheel that installed into a fresh virtual environment using locked dependencies and `uv pip install --no-deps`. Imports were checked to originate inside that environment, outside the source checkout. Running the 14 packaged reference-agent scenarios in mock mode failed **0/14 passed**: `StaticFiles` could not find `site-packages/reference_agent/web` during `create_app()`.

The source files existed, but setuptools package data only included scenario YAML. Editable installs and source-tree tests therefore missed the installed-package failure. The new `scripts/verify_installed_wheel.py` was run against that old wheel and exited 1 at the same missing directory before changing package metadata. Old reports/logs remain in the controller's `work/ci-m0-resume/a-wheel-consumer.log`, `a-package-red.log`, and `.context/releases/A01/consumer-gate.json`.

## Minimal fix and verification

Package `reference_agent/web/*.html`, `*.js`, and `*.css`. No application logic, model behavior, TTL or threshold changes. The installed consumer checks that imports come from the virtual environment rather than the checkout, starts an in-memory application, verifies three static HTTP responses match their packaged files, and runs all packaged V1 scenarios using mock mode. It disables the telemetry endpoint for this process.

Commands from the controller root:

```powershell
uv build --wheel --offline --out-dir .context/releases/A01-package .worktrees/a01-package
uv pip install --python .context/release-env-A01/Scripts/python.exe --offline --no-deps --reinstall .context/releases/A01-package/llmtest-0.2.0a24.dev0-py3-none-any.whl
.context/release-env-A01/Scripts/python.exe .worktrees/a01-package/scripts/verify_installed_wheel.py --output-dir .context/releases/A01-package/consumer
```

Result: **exit 0; 14/14 scenarios passed; three static resources returned HTTP 200 with exact bytes**, one upstream LangChain deprecation warning. New CI runs the same consumer on Python 3.12 and 3.14 after installing a wheel into locked dependencies without the editable project. Local system is Windows/Python 3.13; Linux CI, independent review, merge, release and environment tracking are separate checkpoints, not implied by this result.

The published package version remains `0.2.0a24.dev0`; no release of this version exists yet, and the defective candidate was not published. No user Docker service/configuration was changed, and no real model, embedding or provider SDK call was used. Local persistent deployment, Dify, real Judge effectiveness and IdP/HTTPS acceptance remain outside this offline wheel check.

Compatibility: public Python APIs and data schemas are unchanged. Reverting package metadata would reintroduce the missing-resource startup failure; revert the follow-up commit only if rolling back the associated release too.

## Independent review follow-up

The first consumer guard rejected every module whose parent was the source root. Review found that this also rejected legitimate installations in the CI checkout's `.venv`. Reproduced in a new checkout-local `.venv`: the old guard failed on its valid `site-packages/llmtest/__init__.py`. The guard now requires the import to lie under this interpreter's `sys.prefix` and `sysconfig` purelib/platlib directories. This supports both external and checkout-local virtual environments while rejecting source/editable imports.

Review also found that merely requiring a nonempty scenario report could accept partial packaged assets. A controlled in-memory loader omitted one scenario: before the guard, 13/13 passed and the consumer incorrectly returned 0. The consumer now verifies the exact 14 expected scenario IDs and count. The same partial input is rejected with exit 1; the complete installed package in the CI layout passes 14/14 with exit 0. This experiment does not remove or modify any real scenario fixture.

Controller logs: `a-package-layout-red.log`, `a-package-layout-green.log`, `a-package-partial-before.log`, `a-package-partial-rejected.log` under `work/ci-m0-resume/`. Only these focused consumer checks were repeated because review changed their validation boundaries; no redundant full regression run was added.