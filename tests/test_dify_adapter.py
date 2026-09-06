import json
import threading
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError

import pytest

from qe_platform.adapters import ApplicationAdapterError, DifyAdapterConfig, DifyChatAdapter


@dataclass
class _Reply:
    status_code: int
    body: bytes
    content_type: str = "application/json"


class _DifyFixture:
    def __init__(self):
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self._responses: deque[_Reply] = deque()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                fixture.requests.append(payload)
                fixture.headers.append(dict(self.headers.items()))
                reply = fixture._responses.popleft()
                self.send_response(reply.status_code)
                self.send_header("Content-Type", reply.content_type)
                self.send_header("Content-Length", str(len(reply.body)))
                self.end_headers()
                self.wfile.write(reply.body)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:%s/v1" % self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def respond(self, status_code: int, payload: Any, *, content_type: str = "application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self._responses.append(_Reply(status_code, body, content_type))

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


@pytest.fixture
def http_dify():
    fixture = _DifyFixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _success(answer="answer", conversation_id="conversation-1", **extra):
    return {"answer": answer, "conversation_id": conversation_id, **extra}


def test_adapter_posts_blocking_request_and_reuses_dify_conversation(http_dify):
    http_dify.respond(
        200,
        _success(
            "first answer",
            message_id="message-1",
            retriever_resources=[{"content": "KB evidence"}],
        ),
    )
    http_dify.respond(200, _success("follow-up answer", message_id="message-2"))
    adapter = DifyChatAdapter(
        DifyAdapterConfig(http_dify.base_url + "/", "secret-key", {"language": "zh-CN"})
    )

    first = adapter.send("first question", user_id="user-1", session_id="session-1")
    second = adapter.send("follow-up question", user_id="user-1", session_id="session-1")

    assert first.answer == "first answer"
    assert first.sources == ["KB evidence"]
    assert first.conversation_id == "conversation-1"
    assert first.trace_id == "message-1"
    assert first.raw_response == {}
    assert first.metadata == {
        "dify_message_id": "message-1",
        "dify_retriever_resource_count": 1,
    }
    assert first.latency is not None and first.latency.total_ms >= 0
    assert second.trace_id == "message-2"
    assert http_dify.requests == [
        {
            "inputs": {"language": "zh-CN"},
            "query": "first question",
            "response_mode": "blocking",
            "user": "user-1",
        },
        {
            "inputs": {"language": "zh-CN"},
            "query": "follow-up question",
            "response_mode": "blocking",
            "user": "user-1",
            "conversation_id": "conversation-1",
        },
    ]
    assert http_dify.headers[0]["Authorization"] == "Bearer secret-key"
    assert http_dify.headers[0]["Content-Type"] == "application/json"


def test_adapter_accepts_metadata_retrieval_resources_and_ignores_invalid_items(http_dify):
    http_dify.respond(
        200,
        _success(
            "answer",
            metadata={
                "retriever_resources": [
                    {"segment_content": "segment evidence"},
                    {"segment": "fallback evidence"},
                    {"content": ""},
                    "invalid",
                ]
            },
        ),
    )

    response = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key")).send(
        "question", user_id="user", session_id="session"
    )

    assert response.sources == ["segment evidence", "fallback evidence"]
    assert response.metadata == {"dify_retriever_resource_count": 2}


def test_adapter_isolates_conversation_ids_by_user_and_platform_session(http_dify):
    http_dify.respond(200, _success("one", "conversation-a"))
    http_dify.respond(200, _success("two", "conversation-b"))
    http_dify.respond(200, _success("three", "conversation-c"))
    http_dify.respond(200, _success("four", "conversation-a"))
    adapter = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key"))

    adapter.send("one", user_id="user-a", session_id="session-1")
    adapter.send("two", user_id="user-a", session_id="session-2")
    adapter.send("three", user_id="user-b", session_id="session-1")
    adapter.send("four", user_id="user-a", session_id="session-1")

    assert "conversation_id" not in http_dify.requests[0]
    assert "conversation_id" not in http_dify.requests[1]
    assert "conversation_id" not in http_dify.requests[2]
    assert http_dify.requests[3]["conversation_id"] == "conversation-a"


@pytest.mark.parametrize("status_code", [401, 503])
def test_adapter_classifies_http_errors_without_leaking_upstream_body(http_dify, status_code):
    http_dify.respond(status_code, {"message": "Bearer secret-key and business message must not leak"})
    adapter = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key"))

    with pytest.raises(ApplicationAdapterError, match="Dify API returned HTTP %s" % status_code) as error:
        adapter.send("business message", user_id="user", session_id="session")

    assert error.value.status_code == status_code
    assert "secret-key" not in str(error.value)
    assert "business message" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        {"answer": "answer"},
        {"answer": 3, "conversation_id": "conversation"},
        {"answer": "answer", "conversation_id": ""},
    ],
)
def test_adapter_rejects_malformed_or_incomplete_success_payloads(http_dify, payload):
    http_dify.respond(200, payload)
    adapter = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key"))

    with pytest.raises(ApplicationAdapterError) as error:
        adapter.send("question", user_id="user", session_id="session")

    assert error.value.status_code == 200
    assert "secret-key" not in str(error.value)
    assert "question" not in str(error.value)


def test_adapter_preserves_success_status_for_malformed_response(http_dify):
    http_dify.respond(201, {"answer": "answer"})
    adapter = DifyChatAdapter(DifyAdapterConfig(http_dify.base_url, "secret-key"))

    with pytest.raises(ApplicationAdapterError, match="Dify returned invalid response") as error:
        adapter.send("question", user_id="user", session_id="session")

    assert error.value.status_code == 201


def test_adapter_classifies_transport_failure_without_disclosing_request(monkeypatch):
    def fail(*_args, **_kwargs):
        raise URLError("network unavailable")

    monkeypatch.setattr("qe_platform.adapters.dify.urlopen", fail)
    adapter = DifyChatAdapter(DifyAdapterConfig("http://dify.test/v1", "secret-key"))

    with pytest.raises(ApplicationAdapterError, match="Dify request failed") as error:
        adapter.send("business message", user_id="user", session_id="session")

    assert error.value.status_code is None
    assert "secret-key" not in str(error.value)
    assert "business message" not in str(error.value)
