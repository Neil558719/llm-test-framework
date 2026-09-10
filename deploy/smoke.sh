#!/usr/bin/env sh
set -eu
base_url="${BASE_URL:-http://localhost:8000}"
report="${SMOKE_REPORT:-reports/smoke.json}"
bearer_token_file="${SMOKE_BEARER_TOKEN_FILE:-}"
mkdir -p "$(dirname "$report")"
headers=""
if [ -n "$bearer_token_file" ]; then
  test -f "$bearer_token_file"
  headers="$(tr -d '\r\n' < "$bearer_token_file")"
fi
request() {
  if [ -n "$headers" ]; then curl -fsS -H "authorization: Bearer $headers" "$@"; else curl -fsS "$@"; fi
}
health="$(request "$base_url/api/health")"
knowledge="$(request -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"如何申请 VPN 权限？","user_id":"U1001"}')"
ticket="$(request -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"我的 VPN 无法连接，设备编号是 PC-1001，请帮我创建工单","user_id":"U1001"}')"
access="$(request -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"申请安装 VPN，理由是远程办公","user_id":"U1001"}')"
python - "$report" "$health" "$knowledge" "$ticket" "$access" <<'PY'
import json
import sys
from pathlib import Path

report, health, knowledge, ticket, access = sys.argv[1:]
health, knowledge, ticket, access = map(json.loads, (health, knowledge, ticket, access))
assert health.get("status") == "ok", health
assert knowledge.get("answer") and knowledge.get("trace_id"), knowledge
assert ticket.get("metadata", {}).get("ticket_status") == "created", ticket
assert any(call.get("name") == "create_ticket" for call in ticket.get("tool_calls", [])), ticket
assert access.get("metadata", {}).get("approval_status") == "pending", access
assert any(call.get("name") == "create_approval" for call in access.get("tool_calls", [])), access
Path(report).write_text(
    json.dumps({"operation": "smoke", "status": "ok", "checks": [
        {"name": "health", "passed": True},
        {"name": "knowledge", "passed": True},
        {"name": "ticket", "passed": True},
        {"name": "access", "passed": True},
    ]}, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
printf 'Smoke passed: 4 checks\n'
