"""
chainledger_core.client
========================

Neutral, read-only on-chain data over Ethereum, built on Google's public
BigQuery dataset (bigquery-public-data.crypto_ethereum). This is the
OSS core referenced throughout the Oculix business plan as the grant
artifact -- published to PyPI as `chainledger-core`, MIT licensed.

GUARDRAIL (non-negotiable, repeated in every Oculix planning document):
every method here returns *metrics*, never a risk score, compliance
flag, or AML/sanctions judgment. See guardrails.py for the code-level
enforcement of that rule on anything this library or a caller generates
as natural-language text.

SCHEMA NOTE: queries below are written against the well-documented public
schema of bigquery-public-data.crypto_ethereum as of this writing. I
can't run these against live BigQuery from where this was written (no
network path to bigquery.googleapis.com in that environment) -- run
`bq show --schema bigquery-public-data:crypto_ethereum.transactions`
(and .token_transfers, .contracts) to confirm column names/types
against the live dataset before relying on this in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


class BigQueryLike(Protocol):
    """The minimal surface of google.cloud.bigquery.Client this module
    depends on -- defined as a Protocol so tests can inject a fake
    without needing real BigQuery credentials or network access."""

    def query(self, sql: str, job_config: "QueryJobConfigLike") -> "QueryJobLike": ...


class QueryJobConfigLike(Protocol):
    pass


class QueryJobLike(Protocol):
    def result(self) -> list: ...


class MaxBytesBilledExceeded(Exception):
    """Raised when a query would scan more data than the caller's
    max_bytes_billed ceiling allows. BigQuery itself enforces this at
    the job level (the query fails server-side) -- this exception wraps
    that failure so callers get a clear, typed error instead of a raw
    BigQuery client exception."""


@dataclass
class AddressFlowMetrics:
    address: str
    tx_count_in: int
    tx_count_out: int
    total_value_in_wei: int
    total_value_out_wei: int
    unique_counterparties: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    lookback_days: int


@dataclass
class TokenTransfer:
    token_address: str
    from_address: str
    to_address: str
    value: str  # kept as string -- ERC-20 values can exceed float precision
    transaction_hash: str
    block_timestamp: datetime


@dataclass
class ContractInfo:
    address: str
    is_contract: bool
    is_erc20: bool
    is_erc721: bool
    first_deployed: Optional[datetime]


# Default ceiling: refuses to run a query that would scan more than this
# many bytes, per the max_bytes_billed guardrail repeated across every
# Oculix planning document. Callers can override per-call, but there is
# no "no limit" default -- that's the point of the guardrail.
#
# FIX (found verifying against live BigQuery before this service's first
# deploy): the original 500 MB default was too low to ever succeed.
# address_flow_metrics()'s default 30-day lookback measured ~8.27 GB
# against a real address (bq --dry_run, 2026-07-20) -- every call would
# have hit MaxBytesBilledExceeded out of the box. transactions/token_transfers
# are time-partitioned by block_timestamp but not clustered by address, so
# BigQuery still scans full columns within each date partition regardless
# of the address filter -- cost scales with lookback_days, not query
# selectivity. 10 GB gives ~20% headroom over the default window while
# still capping worst-case cost (a caller passing the max lookback_days=365
# would still be rejected, which is the guardrail doing its job).
#
# COST NOTE, not yet resolved: at BigQuery on-demand pricing (~$6.25/TiB),
# 8.27 GB is trivial per call (~$0.05), but chainledger's Pro tier is
# advertised at 500,000 calls/day -- if a meaningful fraction of those are
# full address_flow_metrics calls rather than cache hits, that's a real
# unbounded cost exposure, not a rounding error. Worth a real pricing/
# caching decision before Pro-tier traffic is live, not solved by this
# constant alone.
DEFAULT_MAX_BYTES_BILLED = 10_000_000_000  # 10 GB


class ChainLedgerClient:
    def __init__(self, bq_client: BigQueryLike, *, dataset: str = "bigquery-public-data.crypto_ethereum"):
        self._bq = bq_client
        self._dataset = dataset

    def _run(self, sql: str, params: dict, max_bytes_billed: int):
        """Every query in this class goes through here, so
        max_bytes_billed is enforced in exactly one place, not
        re-implemented per method."""
        from google.cloud import bigquery  # deferred import: keeps the

        # Protocol-based fakes usable in tests without the real package installed
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(k, _bq_param_type(v), v) for k, v in params.items()
            ],
            maximum_bytes_billed=max_bytes_billed,
        )
        try:
            return list(self._bq.query(sql, job_config=job_config).result())
        except Exception as err:  # BigQuery raises a generic Forbidden/BadRequest for this
            if "bytes billed" in str(err).lower() or "maximumbytesbilled" in str(err).lower():
                raise MaxBytesBilledExceeded(
                    f"Query would exceed the {max_bytes_billed}-byte cap. "
                    "Narrow the lookback window or raise max_bytes_billed explicitly."
                ) from err
            raise

    def address_flow_metrics(
        self, address: str, *, lookback_days: int = 30, max_bytes_billed: int = DEFAULT_MAX_BYTES_BILLED
    ) -> AddressFlowMetrics:
        address = _normalize_address(address)
        sql = f"""
            SELECT
              COUNTIF(to_address = @address) AS tx_count_in,
              COUNTIF(from_address = @address) AS tx_count_out,
              SUM(IF(to_address = @address, CAST(value AS BIGNUMERIC), 0)) AS total_value_in,
              SUM(IF(from_address = @address, CAST(value AS BIGNUMERIC), 0)) AS total_value_out,
              COUNT(DISTINCT IF(to_address = @address, from_address, to_address)) AS unique_counterparties,
              MIN(block_timestamp) AS first_seen,
              MAX(block_timestamp) AS last_seen
            FROM `{self._dataset}.transactions`
            WHERE (to_address = @address OR from_address = @address)
              AND block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @lookback_days DAY)
        """
        rows = self._run(sql, {"address": address, "lookback_days": lookback_days}, max_bytes_billed)
        row = rows[0] if rows else _empty_flow_row()
        return AddressFlowMetrics(
            address=address,
            tx_count_in=int(row["tx_count_in"] or 0),
            tx_count_out=int(row["tx_count_out"] or 0),
            total_value_in_wei=int(row["total_value_in"] or 0),
            total_value_out_wei=int(row["total_value_out"] or 0),
            unique_counterparties=int(row["unique_counterparties"] or 0),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            lookback_days=lookback_days,
        )

    def token_transfers(
        self, address: str, *, limit: int = 50, max_bytes_billed: int = DEFAULT_MAX_BYTES_BILLED
    ) -> list[TokenTransfer]:
        address = _normalize_address(address)
        limit = min(limit, 500)  # hard ceiling regardless of what a caller passes
        sql = f"""
            SELECT token_address, from_address, to_address, value, transaction_hash, block_timestamp
            FROM `{self._dataset}.token_transfers`
            WHERE from_address = @address OR to_address = @address
            ORDER BY block_timestamp DESC
            LIMIT @limit
        """
        rows = self._run(sql, {"address": address, "limit": limit}, max_bytes_billed)
        return [
            TokenTransfer(
                token_address=r["token_address"],
                from_address=r["from_address"],
                to_address=r["to_address"],
                value=str(r["value"]),
                transaction_hash=r["transaction_hash"],
                block_timestamp=r["block_timestamp"],
            )
            for r in rows
        ]

    def contract_info(self, address: str, *, max_bytes_billed: int = DEFAULT_MAX_BYTES_BILLED) -> ContractInfo:
        address = _normalize_address(address)
        sql = f"""
            SELECT address, is_erc20, is_erc721, block_timestamp
            FROM `{self._dataset}.contracts`
            WHERE address = @address
            LIMIT 1
        """
        rows = self._run(sql, {"address": address}, max_bytes_billed)
        if not rows:
            return ContractInfo(address=address, is_contract=False, is_erc20=False, is_erc721=False, first_deployed=None)
        row = rows[0]
        return ContractInfo(
            address=address,
            is_contract=True,
            is_erc20=bool(row["is_erc20"]),
            is_erc721=bool(row["is_erc721"]),
            first_deployed=row["block_timestamp"],
        )

    def wallet_label(self, metrics: AddressFlowMetrics) -> str:
        """A neutral, descriptive bucket -- activity volume only.
        Deliberately NOT a risk/compliance label. See guardrails.py;
        this method's output is exactly the kind of text that should
        pass assert_neutral_language()."""
        total_tx = metrics.tx_count_in + metrics.tx_count_out
        if total_tx == 0:
            return "no activity in window"
        if total_tx < 10:
            return "low-frequency"
        if total_tx < 200:
            return "moderate-frequency"
        return "high-frequency"


def _normalize_address(address: str) -> str:
    address = address.strip().lower()
    if not address.startswith("0x") or len(address) != 42:
        raise ValueError(f"'{address}' doesn't look like a valid Ethereum address (expected 0x + 40 hex chars)")
    return address


def _empty_flow_row() -> dict:
    return {
        "tx_count_in": 0, "tx_count_out": 0, "total_value_in": 0, "total_value_out": 0,
        "unique_counterparties": 0, "first_seen": None, "last_seen": None,
    }


def _bq_param_type(value) -> str:
    if isinstance(value, int):
        return "INT64"
    return "STRING"
