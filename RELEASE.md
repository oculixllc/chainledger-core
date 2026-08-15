<!-- path-declared -->
> **File path:** `RELEASE.md`

# Release Process

1. Update `version` in `pyproject.toml` and add an entry to `CHANGELOG.md`.
2. `poetry run pytest && poetry run ruff check src/ tests/` -- must be clean.
3. Commit: `git commit -am "Release vX.Y.Z"`
4. Tag: `git tag vX.Y.Z && git push origin main --tags`
5. Pushing the tag triggers `.github/workflows/publish.yml`, which builds
   and publishes to PyPI automatically. No manual `poetry publish` needed
   or wanted -- keep the token server-side in Actions secrets only.

First release (v0.1.0) is the one that starts the foundation grant clock
per the Business & Financial Addendum's Phase 1 timeline -- don't tag it
until the neutral-language audit below has actually been run, not just
assumed clean.

## Neutral-language audit scope (before tagging)

Running `chainledger_core.guardrails.find_violations()` against every file
will flag README.md, this file, and client.py's own module docstring --
they legitimately *name* the banned terms while explaining the rule
(e.g. "this library never returns a risk score"). That's expected, not
a violation. The audit that actually matters before a release:

- Any *product-facing* copy: the ChainLedgerAI domain, marketing pages,
  chainledger_api's actual HTTP responses and error messages
- Anything framed as example *output* rather than a description of the
  rule (a README usage example showing a real API response, not prose
  explaining what the guardrail blocks)

If unsure whether a match is a meta-reference or a real violation, read
the surrounding sentence -- "never returns X" is explaining the rule;
"here is X" is breaking it.
