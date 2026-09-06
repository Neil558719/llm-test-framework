import json
import threading
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from qe_platform.adapters import DifyAdapterConfig
from qe_platform.dify_gate import main, run_gate


ASSETS = "qe_platform/scenarios/assets/dify"
_SECRET = "m14-dify-secret"
_QUESTION = "M14_DIFY_PRIVATE_QUESTION"


@dataclass
class _Reply:
    status_code: int
    payload: dict[str, Any]


class _DifyFixture:
    def __init__(self):
        self.requests: list[dict[str, Any]] = []
        self._responses: deque[_Reply] = deque()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                fixture.requests.append(json.loads(self.rfile.read(content_length).decode("utf-8")))
                response = fixture._responses.popleft()
                body = json.dumps(response.payload).encode("utf-8")
                self.send_response(response.status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:%s/v1" % self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def respond(self, answer: str, conversation_id: str, *, sources: list[dict[str, str]] | None = None):
        payload: dict[str, Any] = {
            "answer": answer,
            "conversation_id": conversation_id,
            "message_id": "message-%s" % len(self._responses),
        }
        if sources is not None:
            payload["retriever_resources"] = sources
        self._responses.append(_Reply(200, payload))

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


def _pass_responses(http_dify):
    http_dify.respond("第一轮已收到", "conversation-1")
    http_dify.respond("下一步请提交订单号", "conversation-1")
    http_dify.respond("知识库政策：支持七天退货", "knowledge-conversation", sources=[{"content": "七天退货政策"}])


def test_dify_gate_runs_packaged_scenarios_and_writes_sanitized_capability_report(http_dify, tmp_path):
    _pass_responses(http_dify)

    code = run_gate(
        asset_dir=ASSETS,
        config=DifyAdapterConfig(http_dify.base_url, _SECRET),
        json_path=tmp_path / "dify.json",
        html_path=tmp_path / "dify.html",
    )

    json_text = (tmp_path / "dify.json").read_text(encoding="utf-8")
    html_text = (tmp_path / "dify.html").read_text(encoding="utf-8")
    payload = json.loads(json_text)
    assert code == 0
    assert payload["gate_passed"] is True
    assert payload["total"] == 2
    assert payload["passed"] == 2
    assert payload["capabilities"]["chat_blocking"]["status"] == "supported"
    assert "streaming_ttft" in payload["limitations"]
    assert _SECRET not in json_text + html_text
    assert _QUESTION not in json_text + html_text
    assert "知识库政策" not in json_text + html_text
    assert http_dify.requests[1]["conversation_id"] == "conversation-1"


def test_dify_gate_returns_failed_gate_code_for_response_assertion_failure(http_dify, tmp_path):
    http_dify.respond("第一轮已收到", "conversation-1")
    http_dify.respond("下一步请提交订单号", "conversation-1")
    http_dify.respond("错误政策", "knowledge-conversation", sources=[{"content": "七天退货政策"}])

    code = run_gate(
        asset_dir=ASSETS,
        config=DifyAdapterConfig(http_dify.base_url, _SECRET),
        json_path=tmp_path / "dify.json",
        html_path=tmp_path / "dify.html",
    )

    assert code == 3
    assert json.loads((tmp_path / "dify.json").read_text(encoding="utf-8"))["gate_passed"] is False


def test_dify_gate_cli_returns_configuration_code_without_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    code = main(["--assets", ASSETS, "--json", str(tmp_path / "dify.json"), "--html", str(tmp_path / "dify.html")])

    assert code == 2
    assert not (tmp_path / "dify.json").exists()


def test_dify_gate_cli_does_not_accept_api_key_argument():
    with pytest.raises(SystemExit) as exit_info:
        main(["--api-key", "secret"])

    assert exit_info.value.code == 2
