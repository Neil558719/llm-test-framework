"""Non-sensitive fixture data for a self-contained deployment smoke drill."""

from __future__ import annotations

from .app import create_app
from .services import ApprovalService, AssetService, KnowledgeBase, TicketService, UserService


def create_deployment_app():
    return create_app(
        knowledge_base=KnowledgeBase(
            [{"document_id": "KB-VPN-001", "title": "VPN 使用指引", "content": "VPN Client 用于远程办公访问企业资源。"}]
        ),
        user_service=UserService({"U1001": {"user_id": "U1001", "name": "Smoke User"}}),
        asset_service=AssetService({"PC-1001": {"asset_id": "PC-1001", "owner_id": "U1001", "status": "active"}}),
        ticket_service=TicketService(),
        approval_service=ApprovalService(),
    )
