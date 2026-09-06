import pytest
import time

from qe_platform.adapters import ApplicationAdapterError, ReferenceAgentAdapter
from qe_platform.scenarios import SetupSpec


def _setup(failures=None):
    return SetupSpec(
        user_id="U1001",
        session_id="adapter-1",
        users=[{"user_id": "U1001", "name": "张三"}],
        assets=[{"asset_id": "PC-1001", "owner_id": "U1001", "status": "active"}],
        knowledge=[{"document_id": "kb-1", "title": "VPN", "content": "请重新连接 VPN。"}],
        failures=failures or {},
    )


def test_reference_adapter_returns_envelope_from_chat_api():
    adapter = ReferenceAgentAdapter.from_setup(_setup())

    envelope = adapter.send(
        "VPN 故障，设备 PC-1001，请创建工单",
        user_id="U1001",
        session_id="adapter-1",
    )

    assert envelope.conversation_id == "adapter-1"
    assert envelope.trace_id
    assert envelope.metadata["ticket_status"] == "created"
    assert [call.name for call in envelope.tool_calls] == [
        "query_user",
        "query_asset",
        "create_ticket",
    ]
    assert envelope.tool_calls[-1].result["ticket_id"] == "T-0001"
    assert envelope.latency is not None
    assert envelope.raw_response == {}


def test_reference_adapter_applies_setup_failure_configuration():
    adapter = ReferenceAgentAdapter.from_setup(
        _setup({"ticket": {"status_code": 500, "message": "ticket unavailable"}})
    )

    envelope = adapter.send(
        "VPN 故障，设备 PC-1001，请创建工单",
        user_id="U1001",
        session_id="adapter-failure",
    )

    assert envelope.metadata["ticket_status"] == "unavailable"
    assert envelope.tool_calls[-1].status == "failed"
    assert envelope.tool_calls[-1].error == "ticket unavailable"


def test_reference_adapter_uses_setup_knowledge_records():
    adapter = ReferenceAgentAdapter.from_setup(_setup())

    envelope = adapter.send("如何处理 VPN？", user_id="U1001", session_id="knowledge-1")

    assert envelope.sources == ["kb-1"]
    assert "重新连接" in envelope.answer


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = "unsafe upstream body"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Client:
    def __init__(self, response):
        self.response = response

    def post(self, path, json):
        assert path == "/api/chat"
        return self.response


def test_reference_adapter_wraps_non_success_status_safely():
    adapter = ReferenceAgentAdapter(_Client(_Response(503)))

    with pytest.raises(ApplicationAdapterError) as exc_info:
        adapter.send("hello", user_id="U1001", session_id="s1")

    assert exc_info.value.status_code == 503
    assert "unsafe upstream body" not in str(exc_info.value)


def test_reference_adapter_wraps_malformed_json_safely():
    adapter = ReferenceAgentAdapter(_Client(_Response(200, ValueError("secret payload"))))

    with pytest.raises(ApplicationAdapterError, match="invalid JSON response"):
        adapter.send("hello", user_id="U1001", session_id="s1")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"answer": "ok", "sources": "not-a-list", "tool_calls": []},
        {"answer": "ok", "sources": [], "tool_calls": [{"arguments": {}}]},
    ],
)
def test_reference_adapter_rejects_incomplete_or_invalid_success_payload(payload):
    adapter = ReferenceAgentAdapter(_Client(_Response(200, payload)))
    with pytest.raises(ApplicationAdapterError, match="invalid JSON response"):
        adapter.send("hello", user_id="U1001", session_id="s1")


def test_reference_adapter_applies_yaml_setup_delay():
    setup = _setup({"knowledge": {"delay_seconds": 0.01}})
    adapter = ReferenceAgentAdapter.from_setup(setup)
    started = time.perf_counter()
    adapter.send("如何处理 VPN？", user_id="U1001", session_id="delay")
    assert time.perf_counter() - started >= 0.01
