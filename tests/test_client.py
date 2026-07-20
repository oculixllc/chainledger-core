import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chainledger_core.client import (
    AddressFlowMetrics,
    ChainLedgerClient,
    MaxBytesBilledExceeded,
)

VALID_ADDR = "0x" + "a" * 40


class FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeBigQueryClient:
    """Fake matching the BigQueryLike protocol. `responder` is a
    function (sql, job_config) -> list[dict] so each test controls
    exactly what comes back without touching real BigQuery."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    def query(self, sql, job_config):
        self.calls.append({"sql": sql, "job_config": job_config})
        return FakeJob(self._responder(sql, job_config))


def test_normalizes_and_validates_address():
    fake = FakeBigQueryClient(lambda sql, cfg: [])
    client = ChainLedgerClient(fake)
    with pytest.raises(ValueError):
        client.address_flow_metrics("not-an-address")


def test_address_flow_metrics_happy_path():
    row = {
        "tx_count_in": 12, "tx_count_out": 4,
        "total_value_in": 5_000_000_000_000_000_000,
        "total_value_out": 1_000_000_000_000_000_000,
        "unique_counterparties": 9,
        "first_seen": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "last_seen": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    fake = FakeBigQueryClient(lambda sql, cfg: [row])
    client = ChainLedgerClient(fake)
    metrics = client.address_flow_metrics(VALID_ADDR, lookback_days=90)

    assert isinstance(metrics, AddressFlowMetrics)
    assert metrics.tx_count_in == 12
    assert metrics.tx_count_out == 4
    assert metrics.unique_counterparties == 9
    assert metrics.lookback_days == 90
    assert metrics.address == VALID_ADDR  # already lowercase, unchanged


def test_address_flow_metrics_no_rows_returns_zeroed_result_not_an_error():
    fake = FakeBigQueryClient(lambda sql, cfg: [])
    client = ChainLedgerClient(fake)
    metrics = client.address_flow_metrics(VALID_ADDR)
    assert metrics.tx_count_in == 0
    assert metrics.first_seen is None


def test_max_bytes_billed_is_passed_to_job_config():
    seen_configs = []

    def responder(sql, cfg):
        seen_configs.append(cfg)
        return []

    fake = FakeBigQueryClient(responder)
    client = ChainLedgerClient(fake)
    client.address_flow_metrics(VALID_ADDR, max_bytes_billed=123_456)

    assert len(seen_configs) == 1
    assert seen_configs[0].maximum_bytes_billed == 123_456


def test_exceeding_max_bytes_billed_raises_typed_exception_not_a_raw_client_error():
    def responder(sql, cfg):
        raise Exception("Query exceeded limit for bytes billed: maximumBytesBilled")

    fake = FakeBigQueryClient(responder)
    client = ChainLedgerClient(fake)
    with pytest.raises(MaxBytesBilledExceeded):
        client.address_flow_metrics(VALID_ADDR, max_bytes_billed=1)


def test_token_transfers_limit_is_hard_capped_at_500_regardless_of_caller():
    def responder(sql, cfg):
        limit_param = next(p.value for p in cfg.query_parameters if p.name == "limit")
        assert limit_param == 500  # the cap, not the caller's oversized ask
        return []

    fake = FakeBigQueryClient(responder)
    client = ChainLedgerClient(fake)
    client.token_transfers(VALID_ADDR, limit=999_999)


def test_wallet_label_buckets_are_neutral_activity_only():
    zero = AddressFlowMetrics(VALID_ADDR, 0, 0, 0, 0, 0, None, None, 30)
    low = AddressFlowMetrics(VALID_ADDR, 3, 2, 0, 0, 2, None, None, 30)
    high = AddressFlowMetrics(VALID_ADDR, 150, 100, 0, 0, 40, None, None, 30)

    client = ChainLedgerClient(FakeBigQueryClient(lambda sql, cfg: []))
    assert client.wallet_label(zero) == "no activity in window"
    assert client.wallet_label(low) == "low-frequency"
    assert client.wallet_label(high) == "high-frequency"

    # Guardrail check baked into the test itself: none of these labels
    # should ever contain risk/compliance language.
    from chainledger_core.guardrails import find_violations
    for label in (client.wallet_label(zero), client.wallet_label(low), client.wallet_label(high)):
        assert find_violations(label) == []
