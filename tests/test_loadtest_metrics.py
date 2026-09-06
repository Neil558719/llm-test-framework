from qe_platform.loadtest.models import LoadTestConfig, SampleResult
from qe_platform.loadtest.metrics import summarize


def test_summary_reports_latency_percentiles_throughput_errors_and_cost():
    config = LoadTestConfig(target_url="http://test", requests=4, concurrency=2)
    samples = [
        SampleResult(True, 100, 20, status_code=200, prompt_tokens=10, completion_tokens=5, cost_total=0.1),
        SampleResult(True, 200, 40, status_code=200, prompt_tokens=20, completion_tokens=10, cost_total=0.2),
        SampleResult(False, 300, None, status_code=429, error_type="http_error"),
        SampleResult(False, 400, None, error_type="timeout"),
    ]
    summary = summarize(samples, config, wall_time_ms=1000)
    assert summary.completed == 4
    assert summary.succeeded == 2
    assert summary.throughput_rps == 4.0
    assert summary.error_rate == 0.5
    assert summary.rate_429 == 0.25
    assert summary.latency_ms["p50"] == 250.0
    assert summary.latency_ms["p95"] == 385.0
    assert summary.ttft_ms["p50"] == 30.0
    assert summary.total_tokens == 45
    assert summary.cost_total == 0.3


def test_summary_counts_interrupted_streams_and_empty_percentiles():
    config = LoadTestConfig(target_url="http://test", requests=1, concurrency=1, protocol="sse")
    summary = summarize([SampleResult(False, 10, None, stream_interrupted=True, error_type="stream_interrupted")], config, wall_time_ms=10)
    assert summary.stream_interruption_rate == 1.0
    assert summary.latency_ms == {"p50": 10.0, "p95": 10.0, "p99": 10.0}


def test_summary_does_not_sum_incompatible_currencies():
    config = LoadTestConfig(target_url="http://test", requests=2)
    samples = [
        SampleResult(True, 10, None, cost_total=1.0, cost_currency="USD", price_version="p1"),
        SampleResult(True, 20, None, cost_total=7.0, cost_currency="CNY", price_version="p1"),
    ]
    summary = summarize(samples, config, wall_time_ms=20)
    assert summary.cost_total is None
    assert summary.cost_currency == "MIXED"


def test_summary_marks_partial_success_cost_data_unavailable():
    config = LoadTestConfig(target_url="http://test", requests=2)
    samples = [
        SampleResult(
            True,
            10,
            None,
            cost_total=0.0,
            cost_currency="USD",
            price_version="p1",
        ),
        SampleResult(True, 20, None, cost_total=None),
    ]

    summary = summarize(samples, config, wall_time_ms=20)

    assert summary.cost_total is None
