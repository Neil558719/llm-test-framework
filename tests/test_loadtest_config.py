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


def test_public_config_redacts_url_userinfo_and_sensitive_query_values(tmp_path):
    path = tmp_path / "secret-url.yaml"
    path.write_text(
        "target_url: https://user:password@example.test/path?api_key=secret&region=cn&token=hidden\n",
        encoding="utf-8",
    )
    public = load_config(path).as_public_dict()
    assert public["target_url"] == "https://example.test/path?api_key=%5BREDACTED%5D&region=cn&token=%5BREDACTED%5D"
    assert "password" not in str(public)
    assert "secret" not in str(public)
    assert "hidden" not in str(public)


def test_public_config_redacts_broad_secret_query_names_and_drops_fragment(tmp_path):
    path = tmp_path / "more-secret-url.yaml"
    path.write_text(
        "target_url: https://user:pw@example.test/path?client_secret=abc&password=x&signature=z&region=cn#access_token=frag\n",
        encoding="utf-8",
    )
    public_url = load_config(path).as_public_dict()["target_url"]
    assert "abc" not in public_url and "password=x" not in public_url
    assert "signature=z" not in public_url and "frag" not in public_url
    assert "region=cn" in public_url
    assert "#" not in public_url


@pytest.mark.parametrize(
    "field,value",
    [("requests", '"5"'), ("concurrency", '"2"'), ("timeout_seconds", '"slow"')],
)
def test_load_config_normalizes_invalid_scalar_types_to_value_error(tmp_path, field, value):
    path = tmp_path / "bad-type.yaml"
    path.write_text(f"target_url: http://localhost:8000\n{field}: {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        load_config(path)


@pytest.mark.parametrize(
    "field,value",
    [("target_url", "1"), ("protocol", "[]"), ("user_id", "1"),
     ("message", "{}"), ("json_report", "1"), ("html_report", "[]")],
)
def test_load_config_rejects_invalid_text_scalar_types(tmp_path, field, value):
    path = tmp_path / "bad-text-type.yaml"
    path.write_text(f"target_url: http://localhost:8000\n{field}: {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        load_config(path)


def test_load_config_rejects_invalid_url_port_during_configuration(tmp_path):
    path = tmp_path / "bad-port.yaml"
    path.write_text("target_url: https://example.test:99999/\n", encoding="utf-8")
    with pytest.raises(ValueError, match="target_url"):
        load_config(path)


def test_load_config_rejects_non_string_mapping_keys(tmp_path):
    path = tmp_path / "bad-key.yaml"
    path.write_text("target_url: http://localhost:8000\n1: invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="keys must be strings"):
        load_config(path)


def test_public_config_preserves_ipv6_brackets():
    from qe_platform.loadtest.models import LoadTestConfig

    public = LoadTestConfig(target_url="http://[::1]:8000").as_public_dict()
    assert public["target_url"] == "http://[::1]:8000"


def test_public_config_redacts_test_fault_control_headers():
    from qe_platform.loadtest.models import LoadTestConfig

    public = LoadTestConfig(
        target_url="http://test",
        headers={
            "X-QE-Test-Token": "top-secret",
            "X-QE-Fault": '{"type":"database_error"}',
        },
    ).as_public_dict()

    assert public["headers"] == {
        "X-QE-Test-Token": "[REDACTED]",
        "X-QE-Fault": "[REDACTED]",
    }
    assert "top-secret" not in str(public)
    assert "database_error" not in str(public)


def test_public_config_redacts_sensitive_header_names_and_preserves_benign_values():
    from qe_platform.loadtest.models import LoadTestConfig

    public = LoadTestConfig(
        target_url="http://test",
        headers={
            "Cookie": "session=secret",
            "X-Auth-Token": "another-secret",
            "X-Feature-Flag": "internal-cohort",
        },
    ).as_public_dict()

    assert public["headers"] == {
        "Cookie": "[REDACTED]",
        "X-Auth-Token": "[REDACTED]",
        "X-Feature-Flag": "internal-cohort",
    }
