"""Application identifiers and SQL predicates shared by settings and storage."""
from collections.abc import Iterable, Mapping
import json


def valid_identifier(value: object) -> bool:
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and value != "*" and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def application_set(values: Iterable[str]) -> frozenset[str]:
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Iterable):
        raise ValueError("application grants must be a collection of identifiers")
    result = list(values)
    if not all(valid_identifier(value) for value in result):
        raise ValueError("application grants must contain nonempty identifiers")
    return frozenset(result)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate application grant key")
        result[key] = value
    return result


def load_grants(text: str):
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("application grants must be valid JSON") from exc


def application_filter(column: str, applications: frozenset[str] | None) -> tuple[str, list[str]]:
    """Compose a parameterized SQL predicate before LIMIT/aggregation."""
    if applications is None:
        return "1 = 1", []
    apps = sorted(application_set(applications))
    if not apps:
        return "0 = 1", []
    return f"{column} IN ({','.join('?' for _ in apps)})", apps