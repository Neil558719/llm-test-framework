#!/usr/bin/env sh
set -eu
base_url="${BASE_URL:-http://localhost:8000}"
report="${SMOKE_REPORT:-reports/smoke.json}"
mkdir -p "$(dirname "$report")"
health="$(curl -fsS "$base_url/api/health")"
knowledge="$(curl -fsS -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"如何申请 VPN 权限？","user_id":"U1001"}')"
ticket="$(curl -fsS -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"我的 VPN 无法连接，设备编号是 PC-1001，请帮我创建工单","user_id":"U1001"}')"
access="$(curl -fsS -X POST "$base_url/api/chat" -H 'content-type: application/json' -d '{"message":"请申请 VPN Client 权限，理由是远程办公","user_id":"U1001"}')"
printf '{"health":%s,"knowledge":%s,"ticket":%s,"access":%s}\n' "$health" "$knowledge" "$ticket" "$access" > "$report"
printf 'Smoke passed: 4 checks\n'
