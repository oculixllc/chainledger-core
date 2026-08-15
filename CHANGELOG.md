<!-- path-declared -->
> **File path:** `CHANGELOG.md`

# Changelog

## [Unreleased]
### Added
- Initial release: `ChainLedgerClient` (address flow metrics, token transfers,
  contract info, neutral wallet labeling) over `bigquery-public-data.crypto_ethereum`.
- `assert_neutral_language()` guardrail enforcing the neutral-data-only rule
  in code, not just in planning docs.
- `max_bytes_billed` enforced on every query, no unbounded-scan code path.
