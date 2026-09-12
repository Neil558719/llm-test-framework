"""Bounded business context retained without user prose."""
from __future__ import annotations

import json

SOFTWARE = ("Admin Console", "VPN", "Slack", "Chrome", "生产数据库")


def access_slots(message: str) -> dict[str, object]:
    software = next((item for item in SOFTWARE if item.lower() in message.lower()), "")
    provided = any(marker in message and message.split(marker, 1)[1].strip(" ：:，,。") for marker in ("理由是", "因为", "用于"))
    return {"software": software, "justification_provided": provided}


def draft_message(slots: dict[str, object]) -> str:
    software = slots.get("software", "")
    software = software if software in SOFTWARE else ""
    return "申请权限" + (" " + software if software else "") + (" 理由是已提供" if slots.get("justification_provided") is True else "")


def encode_draft(message: str) -> str:
    return json.dumps(access_slots(message), ensure_ascii=True, sort_keys=True)


def decode_draft(value: str) -> str:
    try:
        slots = json.loads(value)
    except (ValueError, TypeError):
        slots = access_slots(value)
    return draft_message(slots if isinstance(slots, dict) else {})
