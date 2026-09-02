from llmtest import ResponseEnvelope, ToolCall

from qe_platform.adapters import ApplicationAdapterError
from qe_platform.scenarios import load_scenario_text
from qe_platform.workflow_runner import ScenarioRunner


class SequenceAdapter:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def send(self, message, *, user_id, session_id):
        self.calls.append((message, user_id, session_id))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_runner_reuses_session_and_marks_quality_not_executed():
    adapter = SequenceAdapter([ResponseEnvelope(answer="one"), ResponseEnvelope(answer="two")])
    scenario = load_scenario_text("""
id: s1
name: Multiturn
setup: {user_id: U1001}
conversation:
  - user: one
  - user: two
quality:
  relevance: {min_score: 0.8}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert adapter.calls[0][2] == adapter.calls[1][2] == result.session_id
    assert result.passed is True
    assert result.complete is False
    assert result.quality_checks[0].status == "not_executed"
    assert result.as_dict()["quality_checks"][0]["metric"] == "relevance"


def test_runner_evaluates_step_response_and_business_expectations():
    adapter = SequenceAdapter([ResponseEnvelope(answer="Ticket T-1 created", sources=["kb-1"], metadata={"ticket_status": "created"})])
    scenario = load_scenario_text("""
id: response
name: Response assertions
conversation:
  - user: create
    expect:
      response:
        contains: [Ticket, created]
        not_contains: [failed]
        sources_present: true
      business_state:
        - {path: metadata.ticket_status, operator: equals, value: created}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert result.passed is True
    assert len(result.steps[0].assertions) == 5
    assert result.steps[0].status == "passed"


def test_runner_aggregates_multiturn_tool_contracts():
    adapter = SequenceAdapter([
        ResponseEnvelope(answer="need reason", tool_calls=[ToolCall("query_user", {"user_id": "U1001"})]),
        ResponseEnvelope(answer="pending", tool_calls=[ToolCall("query_user", {"user_id": "U1001"}), ToolCall("create_approval", {"software": "VPN"}, {"status": "pending"})], metadata={"approval_status": "pending"}),
    ])
    scenario = load_scenario_text("""
id: tools
name: Tool aggregation
conversation: [{user: first}, {user: second}]
expect:
  tool_order: [query_user, query_user, create_approval]
  tools:
    - {name: query_user, arguments: {user_id: U1001}}
    - {name: query_user}
    - name: create_approval
      arguments: {software: VPN}
      result_schema: {type: object, required: [status]}
  business_state:
    - {path: metadata.approval_status, value: pending}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert result.passed is True
    assert [call.name for call in result.tool_calls] == ["query_user", "query_user", "create_approval"]
    assert result.final_assertions


def test_runner_records_assertion_failures_and_continues_conversation():
    adapter = SequenceAdapter([ResponseEnvelope(answer="wrong"), ResponseEnvelope(answer="second")])
    scenario = load_scenario_text("""
id: failure
name: Failure collection
conversation:
  - {user: first, expect: {response: {contains: [expected]}}}
  - {user: second}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert result.passed is False
    assert [step.status for step in result.steps] == ["failed", "passed"]
    assert len(adapter.calls) == 2


def test_runner_records_adapter_error_and_stops_dependent_steps():
    adapter = SequenceAdapter([ApplicationAdapterError("service unavailable", 503)])
    scenario = load_scenario_text("""
id: error
name: Adapter error
conversation: [{user: first}, {user: second}]
expect: {response: {contains: [done]}}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert result.passed is False
    assert result.complete is False
    assert len(result.steps) == 1
    assert result.steps[0].status == "error"
    assert "service unavailable" in result.steps[0].error
    assert result.final_assertions[0].passed is False
    assert {item.assertion_type for item in result.final_assertions} >= {
        "execution", "response_contains"
    }


def test_runner_records_response_and_business_assertions_as_failed_after_execution_error():
    adapter = SequenceAdapter([ApplicationAdapterError("service unavailable", 503)])
    scenario = load_scenario_text("""
id: error-assertions
name: Adapter error assertions
conversation: [{user: first}]
expect:
  response: {contains: [done], sources_present: true}
  business_state: [{path: metadata.status, value: ok}]
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    failures = [item for item in result.final_assertions if not item.passed]
    assert {item.assertion_type for item in failures} == {
        "execution", "response_contains", "sources_present", "business_state"
    }
    assert all("execution error" in item.message for item in failures[1:])


def test_runner_matches_declared_tools_by_position_and_checks_final_response():
    adapter = SequenceAdapter([ResponseEnvelope(answer="final response", tool_calls=[ToolCall("actual", {})])])
    scenario = load_scenario_text("""
id: positional
name: Positional
conversation: [{user: first}]
expect:
  tools: [{name: expected}]
  response: {contains: [final]}
""")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)

    assert result.passed is False
    assert any(item.assertion_type == "tool_name" and not item.passed for item in result.final_assertions)
    assert any(item.assertion_type == "response_contains" and item.passed for item in result.final_assertions)
    assert any(item.assertion_type == "tool_arguments" for item in result.final_assertions)
    assert any(item.assertion_type == "tool_status" for item in result.final_assertions)


def test_runner_result_preserves_scenario_identity_and_timestamps():
    adapter = SequenceAdapter([ResponseEnvelope(answer="ok")])
    scenario = load_scenario_text("""
id: identity
name: Identity scenario
conversation: [{user: hello}]
""", source="identity.yaml")[0]

    result = ScenarioRunner(lambda setup: adapter).run(scenario)
    payload = result.as_dict()

    assert payload["scenario_name"] == "Identity scenario"
    assert payload["source"] == "identity.yaml"
    assert payload["started_at"]
    assert payload["finished_at"]


def test_runner_records_adapter_factory_error_as_incomplete_execution():
    scenario = load_scenario_text("""
id: factory-error
name: Factory error
conversation: [{user: hello}]
""")[0]

    def fail_factory(setup):
        raise ApplicationAdapterError("adapter setup failed")

    result = ScenarioRunner(fail_factory).run(scenario)

    assert result.passed is False
    assert result.complete is False
    assert result.steps[0].status == "error"
    assert "adapter setup failed" in result.steps[0].error
