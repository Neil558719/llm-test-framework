from pathlib import Path

import pytest

from qe_platform.scenarios import ScenarioLoadError, load_scenario_text, load_scenarios


VALID = """
id: ticket-1
name: Ticket
tags: [ticket]
setup:
  user_id: U1001
  session_id: session-1
conversation:
  - user: VPN is down
  - user: make it high priority
expect:
  tools:
    - name: create_ticket
      status: succeeded
      arguments: {priority: high}
      arguments_schema: {type: object}
  tool_order: [query_user, query_asset, create_ticket]
  strict_tool_order: true
  business_state:
    - path: metadata.ticket_status
      operator: equals
      value: created
  response:
    contains: [created]
    not_contains: [failed]
    sources_present: false
quality:
  relevance: {min_score: 0.8}
"""


def test_loader_parses_valid_multiturn_asset():
    scenario = load_scenario_text(VALID)[0]

    assert scenario.id == "ticket-1"
    assert scenario.conversation[1].user == "make it high priority"
    assert scenario.expect.tool_order == ["query_user", "query_asset", "create_ticket"]
    assert scenario.expect.tools[0].arguments == {"priority": "high"}
    assert scenario.quality.metrics == {"relevance": {"min_score": 0.8}}
    assert scenario.as_dict()["source"] == "<memory>"


def test_loader_accepts_scenarios_list_and_sorts_directory(tmp_path):
    (tmp_path / "b.yml").write_text("id: b\nname: B\nconversation: [{user: b}]\n", encoding="utf-8")
    (tmp_path / "a.yaml").write_text("scenarios: [{id: a, name: A, conversation: [{user: a}]}]\n", encoding="utf-8")

    scenarios = load_scenarios(tmp_path)

    assert [scenario.id for scenario in scenarios] == ["a", "b"]


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("id: x\nname: X\nconversation: []\n", "conversation"),
        ("id: x\nname: X\nconversation: [{user: hi, extra: true}]\n", "conversation[0]"),
        ("id: x\nname: X\nconversation: [{user: hi}]\nunknown: true\n", "$"),
        ("id: x\nname: X\nconversation: [{user: hi}]\nexpect: {business_state: [{path: status, operator: matches, value: ok}]}\n", "operator"),
        ("id: x\nname: X\nconversation: [{user: hi}]\nexpect: {tools: [{name: t, arguments_schema: {type: invalid}}]}\n", "arguments_schema"),
    ],
)
def test_loader_rejects_invalid_assets_with_source_and_path(text, path):
    with pytest.raises(ScenarioLoadError) as exc_info:
        load_scenario_text(text, source="bad.yaml")

    assert exc_info.value.source == "bad.yaml"
    assert path in exc_info.value.path


def test_loader_wraps_invalid_yaml():
    with pytest.raises(ScenarioLoadError, match="invalid YAML"):
        load_scenario_text("id: [", source="broken.yaml")


def test_loader_rejects_duplicate_ids_across_directory(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text("id: duplicate\nname: X\nconversation: [{user: hi}]\n", encoding="utf-8")

    with pytest.raises(ScenarioLoadError, match="duplicate scenario id"):
        load_scenarios(tmp_path)


@pytest.mark.parametrize("path", ["missing.yaml", "asset.json"])
def test_loader_rejects_missing_or_unsupported_path(tmp_path, path):
    target = tmp_path / path
    if target.suffix == ".json":
        target.write_text("{}", encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenarios(target)


def test_loader_rejects_directory_without_yaml(tmp_path):
    (tmp_path / "readme.txt").write_text("none", encoding="utf-8")
    with pytest.raises(ScenarioLoadError, match="no YAML files"):
        load_scenarios(tmp_path)
