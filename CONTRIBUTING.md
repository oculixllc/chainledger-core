# Contributing to chainledger-core

## Setup
```bash
git clone https://github.com/oculix-ai/chainledger-core
cd chainledger-core
poetry install
```

## Before opening a PR
- `poetry run pytest` -- all tests must pass
- `poetry run ruff check src/ tests/` -- lint must be clean
- New query methods must enforce `max_bytes_billed` through the shared
  `_run()` path in `client.py`, not a one-off implementation
- Any new AI-generated or templated output must pass through
  `assert_neutral_language()` before being returned to a caller

## The one hard rule
Nothing in this library may output AML, sanctions, KYC, fraud-risk, or
compliance-flag language -- not in a docstring, not in a log message, not
in a generated summary. This is a legal positioning requirement for the
whole Oculix ChainLedgerAI product line, not a style preference. If you're
not sure whether something crosses the line, run it through
`guardrails.find_violations()` before opening the PR.
