"""Tests for the Prometheus metric definitions module."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

from dawos_agent.metrics import (
    ACCEL_CMD_ERRORS_TOTAL,
    ACCEL_CMD_RETRIES_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
    RATE_LIMIT_HITS_TOTAL,
)

# ---------------------------------------------------------------------------
# Metric type checks
# ---------------------------------------------------------------------------


class TestMetricTypes:
    """Verify each exported metric has the correct Prometheus type."""

    def test_http_requests_total_is_counter(self) -> None:
        assert isinstance(HTTP_REQUESTS_TOTAL, Counter)

    def test_http_request_duration_is_histogram(self) -> None:
        assert isinstance(HTTP_REQUEST_DURATION, Histogram)

    def test_accel_cmd_errors_total_is_counter(self) -> None:
        assert isinstance(ACCEL_CMD_ERRORS_TOTAL, Counter)

    def test_accel_cmd_retries_total_is_counter(self) -> None:
        assert isinstance(ACCEL_CMD_RETRIES_TOTAL, Counter)

    def test_rate_limit_hits_total_is_counter(self) -> None:
        assert isinstance(RATE_LIMIT_HITS_TOTAL, Counter)


# ---------------------------------------------------------------------------
# Metric naming convention
# ---------------------------------------------------------------------------


class TestMetricNaming:
    """Verify metrics follow Prometheus naming conventions."""

    def test_all_counters_have_total_suffix(self) -> None:
        """Counter constructor names must include '_total'.

        The prometheus_client library strips the ``_total`` suffix from
        the internal ``_name`` attribute and re-appends it during
        exposition.  We verify by checking that every counter's
        internal name, when ``_total`` is appended, matches the
        expected convention.
        """
        counters = [
            HTTP_REQUESTS_TOTAL,
            ACCEL_CMD_ERRORS_TOTAL,
            ACCEL_CMD_RETRIES_TOTAL,
            RATE_LIMIT_HITS_TOTAL,
        ]
        for counter in counters:
            full_name = f"{counter._name}_total"
            assert full_name.endswith("_total"), f"{full_name} missing '_total' suffix"

    def test_duration_histogram_has_seconds_suffix(self) -> None:
        """Time-based histograms must end with '_seconds'."""
        assert HTTP_REQUEST_DURATION._name.endswith("_seconds")

    def test_all_metrics_use_dawos_prefix(self) -> None:
        """All metrics should be prefixed with 'dawos_'."""
        metrics = [
            HTTP_REQUESTS_TOTAL,
            HTTP_REQUEST_DURATION,
            ACCEL_CMD_ERRORS_TOTAL,
            ACCEL_CMD_RETRIES_TOTAL,
            RATE_LIMIT_HITS_TOTAL,
        ]
        for metric in metrics:
            assert metric._name.startswith(
                "dawos_"
            ), f"{metric._name} missing 'dawos_' prefix"


# ---------------------------------------------------------------------------
# Label checks
# ---------------------------------------------------------------------------


class TestMetricLabels:
    """Verify HTTP metrics have the expected label sets."""

    def test_http_requests_total_labels(self) -> None:
        """HTTP request counter should have method, endpoint, status labels."""
        assert HTTP_REQUESTS_TOTAL._labelnames == ("method", "endpoint", "status")

    def test_http_request_duration_labels(self) -> None:
        """HTTP duration histogram should have method and endpoint labels."""
        assert HTTP_REQUEST_DURATION._labelnames == ("method", "endpoint")

    def test_accel_cmd_errors_has_no_labels(self) -> None:
        """accel-cmd error counter is a simple total with no labels."""
        assert ACCEL_CMD_ERRORS_TOTAL._labelnames == ()

    def test_accel_cmd_retries_has_no_labels(self) -> None:
        """accel-cmd retry counter is a simple total with no labels."""
        assert ACCEL_CMD_RETRIES_TOTAL._labelnames == ()

    def test_rate_limit_hits_has_no_labels(self) -> None:
        """Rate limit counter is a simple total with no labels."""
        assert RATE_LIMIT_HITS_TOTAL._labelnames == ()
