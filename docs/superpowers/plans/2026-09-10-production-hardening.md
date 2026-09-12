# Production Readiness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the merged M17 platform so it can be migrated to an independent server by injecting production OIDC, secrets, domain, and deployment parameters without changing business code.

**Architecture:** Add a bounded `qe_platform.auth` layer for generic OIDC/JWKS authentication and four-role authorization; keep machine telemetry ingestion on its existing token. Add versioned SQLite persistence and a separate auth session database, then expose the same migration/backup/restore contract to Windows and Linux deployment scripts. Keep Reference Agent, telemetry, and quality-loop business boundaries intact.

**Tech Stack:** Python 3.9+, FastAPI, SQLite, PyJWT with cryptography support, httpx, Docker Compose, PowerShell, POSIX shell, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-production-hardening-design.md`

## Global Constraints

- Preserve `AppResponse`, existing Reference Agent response shapes, M17 quality-loop APIs, and the machine `X-QE-Telemetry-Token` contract.
- Do not store raw access tokens, refresh tokens, Cookie values, Authorization headers, user prompts, answers, or upstream IdP error bodies.
- Production mode must fail closed when required OIDC, session, database, or secret configuration is missing.
- Use SQLite for this phase; preserve repository interfaces for a later PostgreSQL implementation.
- Do not add FastGPT dependencies, adapters, deployments, tests, or CI jobs.
- Functional regression, UI, load-test, telemetry, and deployment checks remain separate execution modes.
- Every production behavior follows red-green-refactor; every task ends with focused verification and a commit.

---

### Task 1: Production configuration and secret sources

**Files:**
- Create: `qe_platform/production/__init__.py`
- Create: `qe_platform/production/settings.py`
- Create: `qe_platform/production/secrets.py`
- Modify: `qe_platform/telemetry/settings.py`
- Modify: `reference_agent/runtime/config.py`
- Modify: `.env.example`
- Test: `tests/test_production_settings.py`

**Interfaces:**
- `ProductionSettings.from_environment(environ: Mapping[str, str] | None = None) -> ProductionSettings` validates mode, database paths, OIDC settings, cookie settings, retention, and secret references.
- `SecretSource.from_environment(environ: Mapping[str, str], environ_getter: Callable[[str], str | None] | None = None) -> SecretSource` reads a direct environment value or a `/run/secrets/<name>` file, trims one final newline, and never exposes the value in `repr` or error text.
- `ProductionSettings.public_dict() -> dict[str, Any]` returns only non-sensitive deployment metadata.

- [ ] **Step 1: Write failing tests** for production mode rejecting missing `OIDC_ISSUER`, `OIDC_AUDIENCE`, `AUTH_SESSION_SECRET`, and database paths; development mode accepts safe local defaults; secret files override empty environment values; error and repr output never contains secret text.
- [ ] **Step 2: Run the focused test file** with `python -m pytest tests/test_production_settings.py -q`; confirm failures identify missing `qe_platform.production` interfaces.
- [ ] **Step 3: Implement the immutable settings and secret source** with strict URL normalization, positive retention days, absolute/relative database path checks, and safe public serialization.
- [ ] **Step 4: Run focused tests and existing telemetry/runtime settings tests**; verify all pass and no public setting API regresses.
- [ ] **Step 5: Commit** `feat: add production settings and secret sources`.

### Task 2: OIDC authentication, sessions, roles, and CSRF

**Files:**
- Create: `qe_platform/auth/__init__.py`
- Create: `qe_platform/auth/models.py`
- Create: `qe_platform/auth/oidc.py`
- Create: `qe_platform/auth/session.py`
- Create: `qe_platform/auth/dependencies.py`
- Modify: `qe_platform/telemetry/api.py`
- Modify: `reference_agent/app.py`
- Modify: `pyproject.toml`
- Test: `tests/test_auth_oidc.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- `OidcVerifier(metadata_client: OidcMetadataClient, clock: Callable[[], datetime])` exposes `verify_access_token(token: str) -> AuthenticatedPrincipal` and validates issuer, audience, allowed algorithms, subject, expiry, and JWKS key rotation.
- `RoleMapper(claim_name: str, mapping: Mapping[str, str])` exposes `roles_from_claims(claims: Mapping[str, Any]) -> frozenset[str]` and returns only `viewer`, `reviewer`, `releaser`, and `admin`.
- `SessionStore(database: str | Path, clock: Callable[[], datetime])` exposes `create`, `get`, `revoke`, and `delete_expired`; persisted rows contain session ID, subject, roles, expiry, and a CSRF hash only.
- `require_user`, `require_role`, and `require_csrf` are FastAPI dependency factories; denied requests return stable 401/403 responses.

- [ ] **Step 1: Add `PyJWT[crypto]>=2.8,<3.0`** to runtime dependencies and write tests with an in-memory RSA key/JWK fixture, injected metadata client, fixed clock, and no network calls.
- [ ] **Step 2: Run `python -m pytest tests/test_auth_oidc.py tests/test_auth_api.py -q`**; confirm failures cover missing verifier/session interfaces, invalid signature, wrong issuer/audience, expired token, unknown role, CSRF mismatch, and 401/403 behavior.
- [ ] **Step 3: Implement metadata/JWKS caching, JWT verification, role mapping, and session persistence**; use constant-time CSRF hash comparison and redact all exception text.
- [ ] **Step 4: Add OIDC login/callback/logout routes** using state, nonce, and PKCE verifier stored in the session database; use HttpOnly/Secure/SameSite cookies and configurable redirect allowlist.
- [ ] **Step 5: Protect human telemetry, review, promotion, quality-loop, model-profile, and administrative writes** while keeping telemetry ingest routes on `X-QE-Telemetry-Token`; leave local test mode explicitly enabled only when `QE_ENVIRONMENT=development`.
- [ ] **Step 6: Run focused auth/API tests plus existing telemetry, feedback, M16, and M17 tests**; verify legacy machine ingestion and `AppResponse` remain unchanged.
- [ ] **Step 7: Commit** `feat: add oidc authentication and role authorization`.

### Task 3: Versioned SQLite migrations and durable business state

**Files:**
- Create: `qe_platform/storage/migrations.py`
- Create: `qe_platform/storage/sqlite_runtime.py`
- Modify: `reference_agent/storage.py`
- Modify: `reference_agent/services/tickets.py`
- Modify: `reference_agent/services/approvals.py`
- Modify: `reference_agent/app.py`
- Modify: `qe_platform/storage/telemetry.py`
- Modify: `qe_platform/quality_loop/storage.py`
- Test: `tests/test_storage_migrations.py`
- Test: `tests/test_reference_agent_persistence.py`

**Interfaces:**
- `MigrationRunner(connection: sqlite3.Connection, component: str, migrations: Sequence[Migration])` exposes `apply() -> int`, `current_version() -> int`, and rejects a database version greater than the code version.
- `configure_sqlite(connection: sqlite3.Connection) -> None` enables foreign keys, WAL, `synchronous=NORMAL`, and a bounded busy timeout.
- `SQLiteStore(...).migrate()`, `SQLiteStore(...).backup(target)`, and existing `upsert_session/get_session` remain safe under concurrent access.
- Ticket and approval services receive a persistence repository and preserve existing idempotency keys and response fields.

- [ ] **Step 1: Write failing migration tests** for first boot, repeated boot, ordered upgrades, unknown higher version, WAL/foreign-key pragmas, and transaction rollback.
- [ ] **Step 2: Run `python -m pytest tests/test_storage_migrations.py -q`** and confirm the expected missing-runner failures.
- [ ] **Step 3: Implement the shared SQLite runtime and `schema_meta` table** with per-component integer versions and atomic migration transactions.
- [ ] **Step 4: Add failing persistence tests** that create a ticket and approval, close the app, reopen it, and assert state and idempotency survive; include concurrent writes and database fault recovery.
- [ ] **Step 5: Implement durable ticket, approval, and access-draft repositories** without changing graph/tool contracts or `AppResponse` fields.
- [ ] **Step 6: Run persistence, telemetry, feedback, M16, M17, and Reference Agent regression suites**; verify existing SQLite files migrate without data loss.
- [ ] **Step 7: Commit** `feat: add versioned sqlite persistence and migrations`.

### Task 4: Consistent backups, restores, readiness, and metrics

**Files:**
- Create: `qe_platform/ops/__init__.py`
- Create: `qe_platform/ops/backup.py`
- Create: `qe_platform/ops/restore.py`
- Create: `qe_platform/ops/metrics.py`
- Modify: `reference_agent/app.py`
- Modify: `qe_platform/telemetry/api.py`
- Test: `tests/test_production_ops.py`
- Test: `tests/test_health_readiness.py`

**Interfaces:**
- `backup_database(source: Path, target: Path) -> BackupResult` uses SQLite online backup, records source schema versions and SHA-256, and runs integrity check.
- `restore_database(backup: Path, target: Path, expected_versions: Mapping[str, int]) -> RestoreResult` validates checksum, schema compatibility, ownership-independent file content, and integrity before replacement.
- `readiness(repository_bundle) -> ReadinessResult` distinguishes liveness from database/config readiness.
- `MetricsRegistry` exposes counters and latency observations without arbitrary user labels or payload values.

- [ ] **Step 1: Write failing tests** for consistent online backup, corrupted backup rejection, high-version rejection, restore integrity, readiness failure, and secret-free metrics/log fields.
- [ ] **Step 2: Run `python -m pytest tests/test_production_ops.py tests/test_health_readiness.py -q`** and confirm failures.
- [ ] **Step 3: Implement backup/restore/checksum/readiness/metrics helpers** with atomic temporary files and bounded error messages.
- [ ] **Step 4: Add `/api/health/live`, `/api/health/ready`, and a protected metrics endpoint** while retaining `/api/health` compatibility.
- [ ] **Step 5: Run focused ops tests plus deployment and telemetry API regressions**.
- [ ] **Step 6: Commit** `feat: add production backup readiness and metrics`.

### Task 5: Production Compose and configuration hardening

**Files:**
- Create: `docker-compose.production.yml`
- Create: `deploy/migrate.sh`
- Create: `deploy/migrate.ps1`
- Create: `deploy/backup.sh`
- Modify: `deploy/backup.ps1`
- Modify: `deploy/restore.sh`
- Modify: `deploy/rollback.ps1`
- Modify: `deploy/smoke.ps1`
- Modify: `deploy/smoke.sh`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Test: `tests/test_production_deployment.py`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Both platform scripts accept the same logical parameters: database path/volume, image tag or digest, backup path, and report path.
- Production Compose uses non-root UID 10001, read-only application filesystem, explicit `/data` volume, secrets mounts, resource limits, restart policy, and readiness healthcheck.
- `deploy/migrate.*`, `deploy/backup.*`, `deploy/restore.*`, `deploy/rollback.*`, and `deploy/smoke.*` return nonzero on failed precondition or postcondition.

- [ ] **Step 1: Write failing asset tests** for required production variables, no secret literals, non-root, read-only root, volume, healthcheck, resource/restart policy, script parity, and fixed image/digest support.
- [ ] **Step 2: Run deployment asset tests** and confirm the current Compose/scripts fail the new production assertions.
- [ ] **Step 3: Implement production Compose overlay and secret mounts**; keep current local defaults compatible with existing tests and M17 workflows.
- [ ] **Step 4: Implement migration, online backup, restore-check, rollback, and Smoke script parity**; use the same JSON result shape on both operating systems.
- [ ] **Step 5: Run PowerShell syntax, `sh -n`, `docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet`, and deployment asset tests**.
- [ ] **Step 6: Commit** `feat: add portable production deployment assets`.

### Task 6: Integration tests and local production hardening drill

**Files:**
- Modify: `.github/workflows/loadtest.yml`
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_production_hardening_contract.py`
- Create: `docs/deployment/production-readiness-runbook.md`
- Create: `docs/deployment/evidence/2026-09-10-production-hardening.md`
- Modify: `docs/deployment/local-production-drill.md`
- Modify: `README.md`

**Interfaces:**
- The contract uses only temporary SQLite files, generated signing keys, fake OIDC metadata, and ephemeral secret files; it never calls a real IdP, model provider, or public URL.
- The runbook defines preflight, migration, backup, restore, start, readiness, Smoke, rollback, and evidence commands for Windows and Linux.

- [ ] **Step 1: Write the end-to-end failing contract** for OIDC-protected browser/API access, machine telemetry ingestion, durable ticket/approval state, backup/restore, readiness, and redacted metrics.
- [ ] **Step 2: Run `python -m pytest tests/test_production_hardening_contract.py -q`** and confirm missing integration behavior.
- [ ] **Step 3: Implement the smallest wiring changes** in app factories, telemetry app creation, and Compose environment handling.
- [ ] **Step 4: Run the contract in a fresh temporary directory**, then execute the local Docker migration/backup/restart/restore/Smoke drill.
- [ ] **Step 5: Run the full non-UI suite, UI suite, M13/M14/M15/M16/M17 contracts, `compileall`, Compose config, shell/PowerShell checks, and `git diff --check`**.
- [ ] **Step 6: Commit** `test: verify production readiness hardening drill`.

### Task 7: Reviewable delivery and migration handoff

**Files:**
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Modify: `docs/deployment/evidence/2026-09-10-production-hardening.md`
- Modify: `docs/deployment/production-readiness-runbook.md`

- [ ] **Step 1: Review the complete diff independently** for compatibility, secret leakage, scope creep, and FastGPT boundaries.
- [ ] **Step 2: Record exact commands, test counts, image digest, schema versions, backup checksum, Smoke output, rollback output, and remaining server-dependent gaps.**
- [ ] **Step 3: Push the isolated branch and create a PR linked to a new production-hardening Issue.**
- [ ] **Step 4: Wait for all Actions and independent code review; fix every Critical/Important finding with a regression test.**
- [ ] **Step 5: Merge only after acceptance criteria pass, fast-forward local master, and rerun the merged-master verification.**
- [ ] **Step 6: Publish a pre-release only after the merged revision is verified; record that independent-server migration remains pending until the user supplies the environment.**

## Verification Commands

Focused auth/data/ops run:

```powershell
python -m pytest tests/test_production_settings.py tests/test_auth_oidc.py tests/test_auth_api.py tests/test_storage_migrations.py tests/test_reference_agent_persistence.py tests/test_production_ops.py tests/test_health_readiness.py tests/test_production_deployment.py tests/test_production_hardening_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening
```

Full regression and static checks:

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-full
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-ui
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
git diff --check
```

The phase is complete only when the four hardening units, local drill, PR, Actions, independent review, merged-master verification, pre-release, evidence, and issue tracking are complete. Independent-server OIDC/HTTPS and public smoke remain explicitly pending until the server is supplied.
