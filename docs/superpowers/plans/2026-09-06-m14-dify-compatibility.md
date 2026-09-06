# Dify Compatibility Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Deliver a platform-owned, tested and documented Dify Chat blocking compatibility adapter with explicit capabilities and a safe compatibility gate.

Architecture: qe_platform.adapters.dify converts Dify Chat HTTP responses into the existing ResponseEnvelope while Dify session IDs remain private to an adapter instance. A gate loads packaged Dify YAML scenarios through ScenarioRunner, serializes a static capability matrix with JSON/HTML results, and receives CI coverage through a local HTTP contract fixture.

Tech Stack: Python 3.9+, standard-library urllib.request and http.server, dataclasses, existing YAML scenario loader, workflow runner, reporting, pytest, GitHub Actions.

Spec: docs/superpowers/specs/2026-09-06-m14-dify-compatibility-design.md

## Global Constraints

- Dify is a secondary compatibility target; Reference Agent remains the primary SUT.
- Do not change AppResponse, ResponseEnvelope, existing Reference Agent scenarios, or V1 API gate public behavior.
- Do not add FastGPT dependencies, adapters, scenarios, documentation, deployment, or CI work.
- Support only Dify Chat POST /chat-messages in blocking mode. Do not imply streaming, Workflow, Completion, files, multimodal, tools, business state, tokens, costs, model versions, or TTFT.
- A real gate requires DIFY_BASE_URL and DIFY_API_KEY; keys cannot appear in CLI arguments, exceptions, reports, YAML, or committed files.
- All production behavior follows focused red-green TDD and every milestone checkpoint is recorded in the development process document.

---

### Task 1: Dify configuration, capability matrix, and exports

Files:
- Create: qe_platform/adapters/dify.py
- Modify: qe_platform/adapters/__init__.py
- Create: tests/test_dify_adapter_config.py

Interfaces:
- DifyAdapterConfig(base_url: str, api_key: str, inputs: Mapping[str, Any], timeout_seconds: float) with from_environment().
- DifyCapability(key: str, status: str, description: str), DifyCapabilityMatrix.as_dict(), and DIFY_CHAT_CAPABILITY_MATRIX.
- Valid statuses are exactly supported, conditional, and unsupported.

- [ ] Step 1: Write failing configuration tests.

~~~
def test_dify_config_requires_explicit_base_url_and_api_key(monkeypatch):
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DIFY_BASE_URL"):
        DifyAdapterConfig.from_environment()

def test_dify_matrix_declares_boundaries():
    matrix = DIFY_CHAT_CAPABILITY_MATRIX.as_dict()
    assert matrix["chat_blocking"]["status"] == "supported"
    assert matrix["streaming_ttft"]["status"] == "unsupported"
    assert matrix["tool_calls"]["status"] == "unsupported"
~~~

- [ ] Step 2: Verify red state.

Run: python -m pytest -q tests/test_dify_adapter_config.py

Expected: FAIL because Dify models do not exist.

- [ ] Step 3: Implement immutable configuration and matrix.

~~~
@dataclass(frozen=True)
class DifyAdapterConfig:
    base_url: str
    api_key: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> "DifyAdapterConfig":
        base_url = os.environ.get("DIFY_BASE_URL", "").strip().rstrip("/")
        api_key = os.environ.get("DIFY_API_KEY", "").strip()
        if not base_url:
            raise ValueError("DIFY_BASE_URL is required")
        if not api_key:
            raise ValueError("DIFY_API_KEY is required")
        return cls(base_url, api_key, _load_inputs(), _load_timeout())
~~~

_load_inputs accepts only an object from DIFY_INPUTS_JSON; _load_timeout accepts only positive numeric DIFY_TIMEOUT_SECONDS. Export models from qe_platform.adapters.

- [ ] Step 4: Verify focused test and adapter regression.

Run: python -m pytest -q tests/test_dify_adapter_config.py tests/test_reference_agent_adapter.py

Expected: PASS.

- [ ] Step 5: Commit.

Run:
~~~
git add qe_platform/adapters/dify.py qe_platform/adapters/__init__.py tests/test_dify_adapter_config.py
git commit -m "feat: declare Dify compatibility capabilities"
~~~

### Task 2: Chat blocking adapter and HTTP contract

Files:
- Modify: qe_platform/adapters/dify.py
- Create: tests/test_dify_adapter.py

Interfaces:
- DifyChatAdapter(config: DifyAdapterConfig) implements ApplicationAdapter.send(message, *, user_id, session_id) -> ResponseEnvelope.
- It posts JSON to {base_url}/chat-messages and maintains private (user_id, session_id) -> conversation_id state.
- It maps answer, conversation ID, message ID, and top-level or metadata retrieval resources.
- It raises sanitized ApplicationAdapterError for transport, non-2xx, invalid JSON, and malformed success payloads.

- [ ] Step 1: Write failing local HTTP contract tests.

~~~
def test_adapter_posts_blocking_request_then_reuses_conversation(http_dify):
    adapter = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key"))
    first = adapter.send("first", user_id="u1", session_id="s1")
    second = adapter.send("follow up", user_id="u1", session_id="s1")
    assert first.sources == ["KB evidence"]
    assert second.trace_id == "message-2"
    assert http_dify.requests[0]["response_mode"] == "blocking"
    assert "conversation_id" not in http_dify.requests[0]
    assert http_dify.requests[1]["conversation_id"] == "conversation-1"

def test_adapter_does_not_leak_http_error_body(http_dify):
    http_dify.respond(401, {"message": "Bearer secret-key"})
    with pytest.raises(ApplicationAdapterError, match="HTTP 401") as error:
        DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key")).send("x", user_id="u", session_id="s")
    assert "secret-key" not in str(error.value)
~~~

The fixture uses ThreadingHTTPServer and captures JSON plus headers. Add cases for metadata resources, user/session isolation, malformed JSON, missing answer/conversation ID, 401/503, and URL transport errors.

- [ ] Step 2: Verify red state.

Run: python -m pytest -q tests/test_dify_adapter.py

Expected: FAIL because DifyChatAdapter is unavailable.

- [ ] Step 3: Implement the safe adapter.

~~~
def send(self, message: str, *, user_id: str, session_id: str) -> ResponseEnvelope:
    key = (user_id, session_id)
    payload = {"inputs": dict(self.config.inputs), "query": message,
               "response_mode": "blocking", "user": user_id}
    if self._conversation_ids.get(key):
        payload["conversation_id"] = self._conversation_ids[key]
    data = self._post_json(payload)
    conversation_id = _required_string(data, "conversation_id")
    self._conversation_ids[key] = conversation_id
    return ResponseEnvelope(answer=_required_string(data, "answer"),
                            sources=_extract_sources(data),
                            conversation_id=conversation_id,
                            trace_id=_optional_string(data.get("message_id")),
                            raw_response={}, metadata=_safe_metadata(data))
~~~

Use urllib.request.Request with Bearer and JSON headers and record end-to-end latency. Exceptions cannot include body text, payload, or Authorization values.

- [ ] Step 4: Verify focused and workflow regressions.

Run: python -m pytest -q tests/test_dify_adapter.py tests/test_workflow_runner.py tests/test_reference_agent_adapter.py

Expected: PASS.

- [ ] Step 5: Commit.

Run:
~~~
git add qe_platform/adapters/dify.py qe_platform/adapters/__init__.py tests/test_dify_adapter.py
git commit -m "feat: adapt Dify Chat blocking responses"
~~~

### Task 3: Packaged scenarios, report, and gate

Files:
- Create: qe_platform/scenarios/assets/dify/knowledge.yaml
- Create: qe_platform/scenarios/assets/dify/conversation.yaml
- Create: qe_platform/dify_gate.py
- Modify: pyproject.toml
- Create: tests/test_dify_gate.py
- Create: tests/test_m14_dify_assets.py

Interfaces:
- run_gate(*, asset_dir, config, json_path, html_path) -> int.
- build_dify_report(results) -> dict containing normal scenario data, capabilities, limitations, and gate_passed.
- main(argv=None) -> int and installed dify-compat-gate.
- Exit code: 0 pass, 1 execution/report failure, 2 invalid environment configuration, 3 failed assertions.

- [ ] Step 1: Write failing gate and asset tests.

~~~
def test_dify_gate_writes_sanitized_capability_report(http_dify, tmp_path):
    code = run_gate(asset_dir=ASSETS, config=DifyAdapterConfig(http_dify.base_url, "secret-key"),
                    json_path=tmp_path / "dify.json", html_path=tmp_path / "dify.html")
    payload = json.loads((tmp_path / "dify.json").read_text(encoding="utf-8"))
    assert code == 0
    assert payload["gate_passed"] is True
    assert payload["capabilities"]["chat_blocking"]["status"] == "supported"
    assert "secret-key" not in (tmp_path / "dify.json").read_text(encoding="utf-8")

def test_dify_assets_only_assert_observable_fields():
    scenarios = load_scenarios(ASSETS)
    assert {item.id for item in scenarios} == {"dify-knowledge", "dify-conversation"}
    assert all(not item.expect.tools and not item.expect.business_state for item in scenarios)
~~~

- [ ] Step 2: Verify red state.

Run: python -m pytest -q tests/test_dify_gate.py tests/test_m14_dify_assets.py

Expected: FAIL because assets and gate are absent.

- [ ] Step 3: Implement fixed observable scenarios and report.

Create one answer/source scenario and one two-step conversation scenario, using only response text and source presence assertions. In run_gate construct one fresh adapter per scenario through ScenarioRunner(lambda setup: DifyChatAdapter(config)). Serialize the normal RunReport plus DIFY_CHAT_CAPABILITY_MATRIX.as_dict(); derive limitations from conditional and unsupported entries. HTML escapes values and lists boundaries before scenario rows.

- [ ] Step 4: Implement environment-only CLI.

~~~
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dify Chat compatibility scenarios")
    parser.add_argument("--assets", default="qe_platform/scenarios/assets/dify")
    parser.add_argument("--json", default="reports/dify-compatibility.json")
    parser.add_argument("--html", default="reports/dify-compatibility.html")
    args = parser.parse_args(argv)
    try:
        config = DifyAdapterConfig.from_environment()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return run_gate(asset_dir=args.assets, config=config, json_path=args.json, html_path=args.html)
~~~

Do not provide an API key parser option. Register the console entry point in pyproject.toml.

- [ ] Step 5: Verify gate, loader, runner, and V1 regressions.

Run: python -m pytest -q tests/test_dify_gate.py tests/test_m14_dify_assets.py tests/test_scenario_loader.py tests/test_workflow_runner.py tests/test_v1_gate.py

Expected: PASS.

- [ ] Step 6: Commit.

Run:
~~~
git add qe_platform/dify_gate.py qe_platform/scenarios/assets/dify pyproject.toml tests/test_dify_gate.py tests/test_m14_dify_assets.py
git commit -m "feat: add Dify compatibility gate"
~~~

### Task 4: CI, guide, README, and status

Files:
- Modify: .github/workflows/loadtest.yml
- Modify: README.md
- Create: docs/Dify 兼容性测试指南.md
- Modify: docs/AI应用全链路质量平台开发流程.md
- Create: tests/test_m14_docs.py

Interfaces:
- CI runs the Dify offline contract suite without external URL or credentials.
- The guide uses environment-only commands and documents every capability limitation.

- [ ] Step 1: Write failing documentation and workflow tests.

~~~
def test_m14_guide_documents_safe_environment_only_usage():
    guide = Path("docs/Dify 兼容性测试指南.md").read_text(encoding="utf-8")
    assert "DIFY_BASE_URL" in guide
    assert "DIFY_API_KEY" in guide
    assert "不支持" in guide
    assert "--api-key" not in guide
~~~

Also assert the README target exists and the workflow has a named Dify compatibility contract step but contains neither DIFY_API_KEY nor an external Dify URL.

- [ ] Step 2: Verify red state.

Run: python -m pytest -q tests/test_m14_docs.py

Expected: FAIL because the guide and CI step do not exist.

- [ ] Step 3: Implement documentation and CI.

Add a Dify compatibility contract step to .github/workflows/loadtest.yml that runs only local tests. Replace the broken README Dify guide link. Write the guide with the exact capability matrix, report-redaction rules, and the dify-compat-gate command using only environment variables. After local acceptance passes, change milestone 14 to 实现完成（交付进行中） and record Issue #49, changed modules, command results, and pending delivery actions.

- [ ] Step 4: Verify local M14 acceptance.

Run: python -m pytest -q tests/test_m14_docs.py tests/test_dify_adapter_config.py tests/test_dify_adapter.py tests/test_dify_gate.py tests/test_m14_dify_assets.py

Expected: PASS.

- [ ] Step 5: Commit.

Run:
~~~
git add .github/workflows/loadtest.yml README.md "docs/Dify 兼容性测试指南.md" docs/AI应用全链路质量平台开发流程.md tests/test_m14_docs.py
git commit -m "ci: verify Dify compatibility contract"
~~~

### Task 5: Review and delivery lifecycle

Files:
- Create: docs/deployment/evidence/2026-09-06-m14-dify-compatibility.md
- Modify: docs/AI应用全链路质量平台开发流程.md
- Modify external Issue #49, pull request, release, and local deployment state.

- [ ] Step 1: Run full implementation acceptance.

~~~
$m14Temp = Join-Path $env:TEMP ('m14-full-' + [guid]::NewGuid().ToString('N'))
python -m pytest -q --no-report --no-history -p no:cacheprovider --basetemp $m14Temp
python -m qe_platform.v1_gate --json reports/m14-v1.json --html reports/m14-v1.html
python -m pytest -q -m ui --no-report --no-history -p no:cacheprovider --basetemp $m14UiTemp
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
~~~

The Dify gate acceptance is the local HTTP fixture through tests/test_dify_gate.py; never fabricate a real Dify service or expose credentials.

- [ ] Step 2: Independently review the complete diff.

Review session isolation, capability truthfulness, success/error validation, redaction, report rendering, documentation, CI, AppResponse compatibility, and FastGPT exclusion. Add a red test for each finding and repeat affected checks.

- [ ] Step 3: Complete delivery.

Push codex/m14-dify-compatibility, create an Issue #49-linked PR, wait for Actions, obtain independent review, merge only with all checks green, fast-forward local master, publish a prerelease with sanitized assets, verify Reference Agent backup, smoke, health, and SQLite integrity, update evidence/status, close Issue #49, and verify clean local and remote master.
