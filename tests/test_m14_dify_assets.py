from qe_platform.scenarios import load_scenarios


ASSETS = "qe_platform/scenarios/assets/dify"


def test_dify_assets_only_assert_observable_chat_response_fields():
    scenarios = load_scenarios(ASSETS)

    assert {scenario.id for scenario in scenarios} == {"dify-knowledge", "dify-conversation"}
    assert all(not scenario.expect.tools for scenario in scenarios)
    assert all(not scenario.expect.business_state for scenario in scenarios)
    assert all(
        not step.expect or (not step.expect.tools and not step.expect.business_state)
        for scenario in scenarios
        for step in scenario.conversation
    )


def test_dify_assets_have_a_source_observation_and_a_multiturn_conversation():
    scenarios = {scenario.id: scenario for scenario in load_scenarios(ASSETS)}

    assert scenarios["dify-knowledge"].expect.response.sources_present is True
    assert len(scenarios["dify-conversation"].conversation) == 2
