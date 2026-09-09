from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping


def write_quality_json(payload: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def write_quality_html(payload: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = html.escape(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True))
    passed = payload.get("passed")
    status = "PASSED" if passed is True else "FAILED" if passed is False else "QUALITY EVIDENCE"
    color = "#176b2c" if passed is True else "#a11" if passed is False else "#333"
    document = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Quality Loop Evidence</title>"
        "<style>body{font:15px system-ui;margin:2rem;color:#222}pre{white-space:pre-wrap;"
        "background:#f5f5f5;border:1px solid #ddd;padding:1rem}h1{color:"
        + color
        + "}</style></head><body><h1>"
        + status
        + "</h1><pre>"
        + serialized
        + "</pre></body></html>"
    )
    target.write_text(document, encoding="utf-8")
    return target
