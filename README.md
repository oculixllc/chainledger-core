<!-- path-declared -->
> **File path:** `README.md`

# chainledger-core

Neutral, read-only on-chain data over public BigQuery blockchain datasets.
Address and flow metrics, token transfer history, contract detection, and
activity-based wallet labeling -- built for developers who need factual
on-chain data, not a compliance or risk-scoring product.

**This library never returns a risk score, AML flag, or compliance
judgment, and never will.** See [CONTRIBUTING.md](./CONTRIBUTING.md) for
why that's a hard rule, not a style choice.

## Install

```bash
pip install chainledger-core
```

## Usage

```python
from google.cloud import bigquery
from chainledger_core import ChainLedgerClient

bq = bigquery.Client()  # needs BigQuery credentials + a project with
                         # billing enabled to run queries, even against
                         # the public dataset
client = ChainLedgerClient(bq)

metrics = client.address_flow_metrics(
    "0x0000000000000000000000000000000000000000",
    lookback_days=30,
    max_bytes_billed=500_000_000,  # required -- there is no unbounded default
)
print(metrics.tx_count_in, metrics.tx_count_out, metrics.unique_counterparties)
print(client.wallet_label(metrics))  # e.g. "moderate-frequency"

transfers = client.token_transfers("0x0000...", limit=25)
contract = client.contract_info("0x0000...")
```

## The `max_bytes_billed` guardrail

Every query method takes `max_bytes_billed` and enforces it at the
BigQuery job-config level -- a query that would scan more than the
ceiling fails with `MaxBytesBilledExceeded` instead of silently running
up a bill. There's no method or code path that skips this.

## The neutral-language guardrail

```python
from chainledger_core import assert_neutral_language, NeutralLanguageViolation

try:
    assert_neutral_language("This wallet has a high risk score.")
except NeutralLanguageViolation as e:
    print(e.matched_terms)  # ['risk score']
```

Run any AI-generated or templated text describing on-chain activity
through this before returning it to a user. `chainledger_api`'s
`/summarize` endpoint does this on every response.

## Schema note

Queries are written against the documented public schema of
`bigquery-public-data.crypto_ethereum` (`transactions`, `token_transfers`,
`contracts`). Confirm current column names against the live dataset
(`bq show --schema bigquery-public-data:crypto_ethereum.transactions`)
before a first production deploy -- public dataset schemas can drift.

## Development

```bash
poetry install
poetry run pytest
poetry run ruff check src/ tests/
```

Tests run against a fake BigQuery client (see `tests/test_client.py`) --
no GCP credentials or network access needed to run the suite.

## License

MIT. See [LICENSE](./LICENSE).
