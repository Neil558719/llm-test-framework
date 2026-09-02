# Local Production Drill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide a zero-budget, Docker Compose based production-like deployment drill with repeatable smoke, rollback evidence, credential ownership, and migration-ready documentation.

**Architecture:** Build the reference Agent into a minimal Python image and run it with Docker Compose using an externalized environment file and named SQLite volume. Shell scripts will provide build, smoke, backup, and rollback operations; GitHub Actions will validate the image and execute a static deployment-readiness check without requiring production secrets. Actual public production remains pending an independent server.

**Tech Stack:** Docker, Docker Compose, PowerShell and POSIX shell scripts, GitHub Actions, FastAPI/Uvicorn, SQLite.

**Spec:** User-approved zero-budget local production drill design in conversation; project rules in `docs/AI应用全链路质量平台开发流程.md`.

## Global Constraints

- FastGPT remains completely out of scope.
- Reference Agent and test platform remain separate.
- Real API keys, user data, and production data must never enter Git.
- Local Docker Compose is evidence for a production-like drill, not public production.
- Delivery must follow Issue -> branch -> local tests -> Push -> PR -> Actions -> review -> merge -> Release -> deployment/tracking.

### Task 1: Deployment baseline and configuration contract

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Test: `tests/test_deployment_assets.py`

- [x] Write tests asserting files exist, compose has healthcheck and persistent volume, and `.env.example` contains no real secret values.
- [x] Run the focused test and confirm it fails because assets are missing.
- [x] Add the minimal image, compose, ignore, and environment contract.
- [x] Run focused tests and compose config validation.
- [x] Commit the deployment baseline.

### Task 2: Smoke, backup, and rollback tooling

**Files:**
- Create: `deploy/smoke.ps1`
- Create: `deploy/smoke.sh`
- Create: `deploy/backup.ps1`
- Create: `deploy/rollback.ps1`
- Create: `tests/test_deploy_scripts.py`

- [x] Write tests for script presence, safe defaults, and required smoke assertions.
- [x] Run focused tests and confirm the expected red failure.
- [x] Implement scripts with configurable base URL, image tag, compose project, and backup path.
- [x] Run static script checks and a local Docker smoke when Docker is available.
- [x] Commit the tooling.

### Task 3: CI image validation and release evidence

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/container.yml`
- Create: `docs/deployment/local-production-drill.md`
- Create: `docs/deployment/credentials-and-ownership.md`
- Create: `docs/deployment/migration-and-rollback.md`
- Modify: `docs/AI应用全链路质量平台开发流程.md`

- [x] Add CI jobs for Docker build, compose config, and deployment asset checks without requiring secrets.
- [x] Document target environments, credential matrix, single-person role ownership, migration steps, rollback evidence, and explicit production gaps.
- [x] Update the milestone status table with commands and results.
- [x] Run full regression, build, diff, and local drill verification.
- [ ] Commit, push, open PR, wait for Actions, review, merge, publish a release, and record deployment tracking evidence.
