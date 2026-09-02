from fastapi.testclient import TestClient

from reference_agent.deployment import create_deployment_app


def test_deployment_app_seeds_non_sensitive_smoke_business_data(tmp_path, monkeypatch):
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(tmp_path / "agent.db"))
    client = TestClient(create_deployment_app())

    ticket = client.post(
        "/api/chat",
        json={"message": "VPN 无法连接，设备 PC-1001，请创建工单，优先级高", "user_id": "U1001"},
    ).json()
    access = client.post(
        "/api/chat",
        json={"message": "申请安装 VPN，理由是远程办公", "user_id": "U1001"},
    ).json()

    assert ticket["metadata"]["ticket_status"] == "created"
    assert access["metadata"]["approval_status"] == "pending"
