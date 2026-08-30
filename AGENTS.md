# AI Quality Platform Working Agreement

This repository is evolving from an LLM evaluation framework into an AI
application end-to-end quality engineering and automated testing platform.
All implementation, documentation, progress reporting, and scope decisions
must follow `docs/AI应用全链路质量平台开发流程.md`.

## Persistent Product Direction

- The primary system under test is a self-built enterprise IT service desk
  Agent. Dify and OpenAI-compatible applications are secondary compatibility
  targets. FastGPT is explicitly out of scope for this project.
- The system under test and the test platform must remain separated. Do not
  put test assertions into the Agent implementation.
- `llmtest` remains the reusable LLM quality evaluation core. New platform
  capabilities belong in clearly bounded modules rather than being forced
  into the pytest plugin.
- The delivery path has three cumulative releases: core functional and tool
  contract testing, quality-engineering enhancements, and an online quality
  feedback loop. Do not skip prerequisites or claim later-release capability
  before its acceptance criteria pass.
- Do not add FastGPT dependencies, adapters, deployment steps, test cases, or
  CI jobs. Existing FastGPT example files are legacy reference material only
  and must not be extended or used as a release acceptance target.

## Required Workflow

1. Before starting work, read the development-process document and inspect
   the current implementation status table.
2. Work in the dependency order defined there unless the user explicitly
   changes scope.
3. Use test-driven development for production behavior: write and run a
   focused failing test, implement the smallest change, then run focused and
   relevant regression tests.
4. Preserve current public APIs, especially `AppResponse`, unless a
   documented compatibility path is implemented and verified.
5. Functional regression tests, load tests, browser tests, and online
   telemetry are distinct execution modes. Do not force load testing into the
   pytest plugin.
6. Record every completed milestone with evidence: changed modules, command,
   result, and remaining gaps. Update the status table in the development
   process document in the same change set.
7. Use one isolated `codex/` worktree branch for each independently
   reviewable milestone. After that milestone's acceptance criteria and
   regression checks pass, independently inspect the diff, commit it, merge
   it into `master`, and verify the merged `master` state. Do not merge a
   branch with failed, incomplete, or unverified acceptance criteria.

## Release Delivery Lifecycle

Every requirement or defect must follow this delivery chain, in order:

```text
Requirement/defect
-> Issue
-> Branch development
-> Local tests
-> Push to GitHub
-> Pull Request
-> GitHub Actions checks
-> Code review
-> Merge to master
-> Publish Release
-> Deployment and issue tracking
```

Local tests are necessary evidence, but they are not the definition of
completion. A milestone or release cannot be reported as complete, and must
not be marked ready for release, until the applicable GitHub push, Pull
Request, Actions checks, review, merge, Release, and deployment/issue-tracking
steps are complete. If this environment cannot perform a GitHub or deployment
step, report it explicitly as blocked or pending; never imply that it happened.

At every milestone acceptance checkpoint, proactively remind the user of:

1. The current acceptance checkpoint and the evidence already available.
2. The remaining GitHub, review, Release, and deployment/tracking actions.
3. Whether the current evidence satisfies release conditions, and any blocker
   that prevents release.

This lifecycle applies to all subsequent development and remains mandatory in
new conversations working on this project directory.

## Progress Reporting Contract

When asked for development progress, answer against the three releases and
the ordered milestones in the development-process document. State:

1. Current release and milestone.
2. Implemented items, each with verification evidence.
3. In-progress items and exact remaining work.
4. Not-yet-started items.
5. Blockers, risks, or decisions needed from the user.

Do not summarize progress only as a percentage. Do not label a capability as
implemented because it exists in a plan, README, mock, or design document;
it is implemented only after its documented acceptance criteria and tests
pass.
