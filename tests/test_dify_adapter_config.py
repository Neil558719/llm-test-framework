import pytest

from qe_platform.adapters import DIFY_CHAT_CAPABILITY_MATRIX, DifyAdapterConfig


def test_dify_config_requires_explicit_base_url(monkeypatch):
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DIFY_BASE_URL"):
        DifyAdapterConfig.from_environment()


def test_dify_config_requires_explicit_api_key(monkeypatch):
    monkeypatch.setenv("DIFY_BASE_URL", "http://dify.test/v1/")
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DIFY_API_KEY"):
        DifyAdapterConfig.from_environment()


def test_dify_config_reads_normalized_safe_environment_values(monkeypatch):
    monkeypatch.setenv("DIFY_BASE_URL", " https://dify.example/v1/ ")
    monkeypatch.setenv("DIFY_API_KEY", "app-secret")
    monkeypatch.setenv("DIFY_INPUTS_JSON", '{"language":"zh-CN"}')
    monkeypatch.setenv("DIFY_TIMEOUT_SECONDS", "12.5")

    config = DifyAdapterConfig.from_environment()

    assert config.base_url == "https://dify.example/v1"
    assert config.api_key == "app-secret"
    assert dict(config.inputs) == {"language": "zh-CN"}
    assert config.timeout_seconds == 12.5


def test_dify_config_adds_api_version_path_when_base_url_omits_it():
    config = DifyAdapterConfig("https://dify.example", "app-secret")

    assert config.base_url == "https://dify.example/v1"


def test_dify_config_copies_json_inputs_and_rejects_non_json_values():
    original = {"nested": {"language": "zh-CN"}}
    config = DifyAdapterConfig("https://dify.example/v1", "app-secret", original)
    original["nested"]["language"] = "en-US"

    assert config.inputs["nested"]["language"] == "zh-CN"
    with pytest.raises(ValueError, match="DIFY_INPUTS_JSON"):
        DifyAdapterConfig("https://dify.example/v1", "app-secret", {"unsupported": {1, 2}})


@pytest.mark.parametrize("suffix", ["?tenant=private", "#private-fragment"])
def test_dify_config_rejects_base_url_query_or_fragment(suffix):
    with pytest.raises(ValueError, match="query or fragment"):
        DifyAdapterConfig("https://dify.example/v1" + suffix, "app-secret")


@pytest.mark.parametrize("api_key", ["app-secret\r\nInjected: true", "app-secret\nInjected: true"])
def test_dify_config_rejects_api_key_line_breaks(api_key):
    with pytest.raises(ValueError, match="line breaks") as error:
        DifyAdapterConfig("https://dify.example/v1", api_key)

    assert api_key not in str(error.value)


@pytest.mark.parametrize(
    ("inputs", "timeout", "message"),
    [
        ("[]", None, "DIFY_INPUTS_JSON"),
        ("{", None, "DIFY_INPUTS_JSON"),
        (None, "0", "DIFY_TIMEOUT_SECONDS"),
        (None, "not-a-number", "DIFY_TIMEOUT_SECONDS"),
    ],
)
def test_dify_config_rejects_invalid_optional_environment_values(monkeypatch, inputs, timeout, message):
    monkeypatch.setenv("DIFY_BASE_URL", "http://dify.test/v1")
    monkeypatch.setenv("DIFY_API_KEY", "app-secret")
    if inputs is None:
        monkeypatch.delenv("DIFY_INPUTS_JSON", raising=False)
    else:
        monkeypatch.setenv("DIFY_INPUTS_JSON", inputs)
    if timeout is None:
        monkeypatch.delenv("DIFY_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("DIFY_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match=message):
        DifyAdapterConfig.from_environment()


def test_dify_matrix_declares_supported_and_unsupported_boundaries():
    matrix = DIFY_CHAT_CAPABILITY_MATRIX.as_dict()

    assert matrix["chat_blocking"]["status"] == "supported"
    assert matrix["conversation_continuation"]["status"] == "supported"
    assert matrix["retrieval_resources"]["status"] == "conditional"
    assert matrix["streaming_ttft"]["status"] == "unsupported"
    assert matrix["tool_calls"]["status"] == "unsupported"
    assert set(matrix) == {
        "chat_blocking",
        "conversation_continuation",
        "retrieval_resources",
        "authentication_errors",
        "tool_calls",
        "usage_cost_model_version",
        "streaming_ttft",
        "workflow_completion_files_multimodal",
    }
