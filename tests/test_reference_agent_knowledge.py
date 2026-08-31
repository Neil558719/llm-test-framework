"""IT 知识问答流程契约测试。"""

from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.graph import build_graph
from reference_agent.services.common import FailureConfig, ServiceError
from reference_agent.services.knowledge_base import KnowledgeBase


def _knowledge_base() -> KnowledgeBase:
    return KnowledgeBase(
        records=[
            {
                "document_id": "kb-vpn-1",
                "title": "VPN 连接故障排查",
                "content": "请检查账号状态并重新连接 VPN。",
            }
        ]
    )


def test_graph_answers_from_knowledge_base_with_citation():
    result = build_graph(_knowledge_base()).invoke(
        {"message": "VPN 连接故障怎么排查？", "answer": "", "sources": []}
    )

    assert result["answer"] == "根据《VPN 连接故障排查》：请检查账号状态并重新连接 VPN。"
    assert result["sources"] == ["kb-vpn-1"]
    assert result["knowledge_status"] == "answered"


def test_graph_refuses_questions_without_knowledge_match():
    result = build_graph(_knowledge_base()).invoke(
        {"message": "公司食堂今天有什么菜？", "answer": "", "sources": []}
    )

    assert "无法可靠回答" in result["answer"]
    assert result["sources"] == []
    assert result["knowledge_status"] == "refused"


def test_graph_marks_knowledge_service_failure_as_unavailable():
    knowledge_base = KnowledgeBase(failure=FailureConfig(status_code=504, message="timeout"))

    result = build_graph(knowledge_base).invoke(
        {"message": "VPN 怎么连接？", "answer": "", "sources": []}
    )

    assert "暂时不可用" in result["answer"]
    assert result["sources"] == []
    assert result["knowledge_status"] == "unavailable"
    assert result["error"]["status_code"] == 504


def test_chat_api_returns_citations_and_knowledge_status():
    client = TestClient(create_app(":memory:", knowledge_base=_knowledge_base()))

    response = client.post("/api/chat", json={"message": "VPN 连接故障怎么排查？"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == ["kb-vpn-1"]
    assert body["metadata"]["knowledge_status"] == "answered"

