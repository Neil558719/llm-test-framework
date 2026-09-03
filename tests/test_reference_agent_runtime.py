from reference_agent.runtime.agent import AgentRuntime
from reference_agent.runtime import AgentModelConfig, ModelProfile, ModelProviderRegistry


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return next(self.responses)


def test_runtime_passes_validated_hints_and_generates_real_answer():
    fake = FakeClient(['{"intent":"ticket","parameters":{"asset_id":"PC-1001","category":"vpn","priority":"high"}}', '已根据业务结果回复'])
    registry = ModelProviderRegistry()
    registry.register(ModelProfile("fake", "Fake", "real", "openai", "http://stub"), lambda c: fake)
    graph = type("Graph", (), {"invoke": lambda self, state: {"answer": "工单已创建", "tool_calls": [], "sources": []}})()
    runtime = AgentRuntime(graph, AgentModelConfig(profile="fake", mode="real", provider="openai", model="stub", api_key="x"), registry)

    result = runtime.invoke({"message": "VPN 故障", "user_id": "U1001", "session_id": "s1"})

    assert result["answer"] == "已根据业务结果回复"
    assert result["metadata"]["generation_status"] == "model"
    assert len(fake.calls) == 2
