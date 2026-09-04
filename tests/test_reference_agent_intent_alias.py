from reference_agent.runtime.agent import AgentRuntime
from reference_agent.runtime import AgentModelConfig, ModelProfile, ModelProviderRegistry


class FakeClient:
    last_usage = None
    def complete(self, messages, **kwargs):
        return '{"intent":"create_ticket","parameters":{"device":"PC-1001","issue":"VPN无法连接"}}'


def test_runtime_normalizes_common_model_intent_aliases_and_parameters():
    registry = ModelProviderRegistry()
    fake = FakeClient()
    registry.register(ModelProfile("fake", "Fake", "real", "deepseek"), lambda config: fake)
    graph = type("Graph", (), {"invoke": lambda self, state: state})()
    runtime = AgentRuntime(graph, AgentModelConfig(profile="fake", mode="real", provider="deepseek", model="deepseek-chat"), registry)
    result = runtime.invoke({"message": "VPN故障", "user_id": "U1001", "session_id": "s1"})
    assert result["metadata"]["intent"] == "ticket"
    assert result["runtime_hints"]["parameters"]["asset_id"] == "PC-1001"
    assert result["runtime_hints"]["parameters"]["category"] == "vpn"
