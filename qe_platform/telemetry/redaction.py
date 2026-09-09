from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Mapping


_FORBIDDEN_PARTS = ("message", "answer", "authorization", "apikey", "token", "arguments", "result", "rawrequest", "rawresponse", "auth", "secret")
_FORBIDDEN_VALUE_PARTS = ("bearer", "secret", "private", "request", "response", "exception", "authorization", "api key", "token")
_SAFE_SERIALIZED_KEYS = frozenset({
    "traceid", "application", "timestamp", "requestfingerprint", "answerfingerprint", "requestlength", "answerlength",
    "source", "userfingerprint", "sessionfingerprint", "reporterfingerprint", "toolcalls", "name", "status", "metadata",
    "usage", "prompttokens", "completiontokens", "totaltokens", "cost", "input", "output", "total", "inputcost",
    "outputcost", "totalcost", "currency", "priceversion", "modelversion", "provider", "model", "prompt", "knowledgebase",
    "tools", "promptversion", "knowledgebaseversion", "toolschemaversion", "latency", "totalms", "ttftms", "feedbackid", "category", "createdat",
})
_METADATA_KEYS = frozenset({"environment", "request_id", "release", "region", "tenant"})


def fingerprint(value: str, hash_key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("fingerprint value must be nonempty")
    if not isinstance(hash_key, str) or not hash_key:
        raise ValueError("hash_key must be nonempty")
    return hmac.new(hash_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class VersionFingerprint:
    """A version digest produced by hashing, never by accepting a bare digest.

    Incoming labels are always hashed, even when they resemble a digest.
    Neither the raw label nor the key is retained on the object. Controlled
    hydration of persisted trace JSON belongs to the storage boundary, not
    this public ingestion contract.
    """

    digest: str

    def __init__(self, value: str, hash_key: str) -> None:
        object.__setattr__(self, "digest", fingerprint(value, hash_key))


def _normalized_key(key: str) -> str:
    return "".join(char for char in key.lower() if char.isalnum())


def _forbidden_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return normalized not in _SAFE_SERIALIZED_KEYS and any(part in normalized for part in _FORBIDDEN_PARTS)


def assert_sanitized_payload(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload keys must be strings")
            if _forbidden_key(key):
                raise ValueError(f"forbidden field: {key}")
            assert_sanitized_payload(item)
    elif isinstance(value, str):
        normalized = value.lower()
        if any(part in normalized for part in _FORBIDDEN_VALUE_PARTS):
            raise ValueError("forbidden sensitive value")
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_sanitized_payload(item)


def sanitize_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    assert_sanitized_payload(value)
    unknown = sorted(set(value) - _METADATA_KEYS)
    if unknown:
        raise ValueError(f"metadata fields are not whitelisted: {', '.join(unknown)}")
    if not all(isinstance(key, str) and isinstance(item, (str, int, float, bool, type(None))) for key, item in value.items()):
        raise ValueError("metadata values must be scalar")
    return dict(value)
