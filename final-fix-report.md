# Production hardening final-fix verification

Base commit: `03d9a14e969dd5074bb5170e14f71f6c9599e462` (`codex/production-hardening`).

## Review fixes covered

- Production chat endpoints require an authenticated identity and CSRF token,
  bind a new business session atomically to that identity, and deny access by
  a different principal.
- Authorization callback state is bound to an HttpOnly transaction cookie;
  the authenticated-session endpoint and logout behavior are covered.
- Readiness validates configured authentication dependencies, real model
  configuration, writable SQLite storage, integrity, expected schema versions,
  and required tables without disclosing internal failure details.
- Approval justifications and incomplete access drafts retain only safe,
  structured values across persistence, migrations, backups, and responses.
- Bounded process metrics cover HTTP/auth outcomes and backup, restore,
  migration, quality-gate, and database failure paths.
- Deployment scripts preserve ordered Compose files.  The Windows watcher test
  fixture now writes its temporary PowerShell script and captured log as UTF-8
  so it remains valid when the worktree path contains non-ASCII characters.

## Fresh verification evidence

Executed with the repository root virtual environment after installing the
already-declared `PyJWT[crypto]>=2.8,<3.0` dependency (installed version:
`PyJWT 2.13.0`).  The worktree has no separate `.venv`.

```text
C:\Users\ZhuanZ1\Desktop\LLM应用测试框架(backup)\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-final-verification tests/test_final_hardening_fixes.py tests/test_final_deploy_args.py tests/test_auth_api.py tests/test_auth_oidc.py tests/test_health_readiness.py tests/test_reference_agent_persistence.py tests/test_production_hardening_contract.py
54 passed, 53 warnings in 7.10s

C:\Users\ZhuanZ1\Desktop\LLM应用测试框架(backup)\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-watcher-final tests/test_deploy_scripts.py::test_windows_watcher_survives_failed_refresh_and_retries_next_env_save
1 passed in 5.14s

C:\Users\ZhuanZ1\Desktop\LLM应用测试框架(backup)\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-final-ops-final tests/test_production_ops.py tests/test_storage_migrations.py tests/test_production_settings.py tests/test_production_deployment.py tests/test_deploy_scripts.py tests/test_deployment_assets.py
49 passed in 11.90s
```

`git diff --check` was also run before commit.  A full test suite was not run
in this final-fix wave.

## Follow-up review fixes

- Both production chat write endpoints now require the `viewer` role.  The
  existing role model keeps `admin` as a viewer-capable super-role; reviewer
  and releaser authorization remains scoped to their existing endpoints.
  Browser sessions and signed Bearer tokens whose external roles map to no
  internal role receive `403` before a business session can be claimed.
- The Windows readiness drill defines the ordered base-plus-production Compose
  pair once, derives Compose command arguments from it, and passes the same
  `$composeFiles` value to migration, backup, restore, and rollback examples.

The new regressions were first run before implementation:

```text
tests/test_production_hardening_contract.py::test_production_chat_rejects_zero_role_browser_sessions_and_bearer_tokens
tests/test_final_deploy_args.py::test_readiness_runbook_defines_and_reuses_the_production_compose_file_pair
3 failed (two zero-role writes returned 200; Compose pair was undefined)
```

After the minimal fixes, the focused regression command completed with:

```text
C:\Users\ZhuanZ1\Desktop\LLM应用测试框架(backup)\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-final-review-regression tests/test_auth_api.py tests/test_auth_oidc.py tests/test_production_hardening_contract.py tests/test_final_hardening_fixes.py tests/test_final_deploy_args.py tests/test_production_deployment.py tests/test_deploy_scripts.py tests/test_deployment_assets.py
74 passed, 49 warnings in 17.96s
```
