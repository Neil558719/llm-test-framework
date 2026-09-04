import pytest

from qe_platform.loadtest.config import load_config


def test_load_config_validates_and_redacts_auth_headers_from_public_payload(tmp_path):
    path = tmp_path / "load.yaml"
    path.write_text("target_url: http://localhost:8000\nprotocol: sse\nrequests: 3\nconcurrency: 2\nheaders:\n  Authorization: Bearer secret\n", encoding="utf-8")
    config = load_config(path)
    assert config.protocol == "sse"
    assert config.headers["Authorization"] == "Bearer secret"
    assert config.as_public_dict()["headers"]["Authorization"] == "[REDACTED]"


def test_load_config_rejects_invalid_concurrency(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("target_url: http://localhost:8000\nrequests: 1\nconcurrency: 0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="concurrency"):
        load_config(path)


def test_load_config_accepts_duration_instead_of_request_count(tmp_path):
    path = tmp_path / "duration.yaml"
    path.write_text("target_url: http://localhost:8000\nduration_seconds: 0.1\nconcurrency: 2\n", encoding="utf-8")
    config = load_config(path)
    assert config.requests is None
    assert config.duration_seconds == 0.1
