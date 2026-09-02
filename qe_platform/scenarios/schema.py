SCENARIO_SCHEMA = {
    "type": "object", "required": ["id", "name", "conversation"], "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1}, "name": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "setup": {"$ref": "#/$defs/setup"}, "conversation": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/step"}},
        "expect": {"$ref": "#/$defs/expect"}, "quality": {"type": "object"},
    },
    "$defs": {
        "setup": {"type": "object", "additionalProperties": False, "properties": {"user_id": {"type": "string"}, "session_id": {"type": ["string", "null"]}, "users": {"type": "array", "items": {"$ref": "#/$defs/user"}}, "assets": {"type": "array", "items": {"$ref": "#/$defs/asset"}}, "knowledge": {"type": "array", "items": {"$ref": "#/$defs/knowledge"}}, "failures": {"type": "object", "additionalProperties": False, "properties": {name: {"$ref": "#/$defs/failure"} for name in ("user", "asset", "ticket", "approval", "knowledge")}}}},
        "user": {"type": "object", "required": ["user_id"], "additionalProperties": False, "properties": {"user_id": {"type": "string"}, "name": {"type": "string"}}},
        "asset": {"type": "object", "required": ["asset_id", "owner_id"], "additionalProperties": False, "properties": {"asset_id": {"type": "string"}, "owner_id": {"type": "string"}, "status": {"type": "string"}}},
        "knowledge": {"type": "object", "required": ["document_id", "title", "content"], "additionalProperties": False, "properties": {"document_id": {"type": ["string", "number"]}, "title": {"type": "string"}, "content": {"type": "string"}}},
        "failure": {"type": "object", "additionalProperties": False, "properties": {"status_code": {"type": "integer"}, "message": {"type": "string"}, "delay_seconds": {"type": "number", "minimum": 0}}},
        "step": {"type": "object", "required": ["user"], "additionalProperties": False, "properties": {"user": {"type": "string", "minLength": 1}, "expect": {"$ref": "#/$defs/expect"}}},
        "expect": {"type": "object", "additionalProperties": False, "properties": {"tools": {"type": "array", "items": {"$ref": "#/$defs/tool"}}, "tool_order": {"type": "array", "items": {"type": "string"}}, "strict_tool_order": {"type": "boolean"}, "business_state": {"type": "array", "items": {"$ref": "#/$defs/business"}}, "response": {"$ref": "#/$defs/response"}}},
        "tool": {"type": "object", "required": ["name"], "additionalProperties": False, "properties": {"name": {"type": "string", "minLength": 1}, "arguments": {"type": "object"}, "arguments_schema": {"type": "object"}, "result_schema": {"type": "object"}, "status": {"type": "string"}}},
        "business": {"type": "object", "required": ["path"], "additionalProperties": False, "properties": {"path": {"type": "string", "minLength": 1}, "operator": {"type": "string"}, "value": {}}},
        "response": {"type": "object", "additionalProperties": False, "properties": {"contains": {"type": "array", "items": {"type": "string"}}, "not_contains": {"type": "array", "items": {"type": "string"}}, "sources_present": {"type": "boolean"}}},
    },
}
