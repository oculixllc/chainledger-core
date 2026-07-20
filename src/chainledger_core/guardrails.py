"""
chainledger_core.guardrails
=============================

Operationalizes the non-negotiable rule stated in Business Plan v3.1 §6
and repeated in the Terms of Service, GCP Foundation Maximization Plan,
and Brand & Domain Strategy: ChainLedgerAI is neutral on-chain data,
never an AML/sanctions/compliance/risk-scoring tool -- in the product,
the docs, or the domain.

Until now that rule lived only in prose. This module is the code-level
check: anything ChainLedgerAI generates as natural-language text (e.g.
an AI-written summary) gets checked against it before it's returned.
"""

import re

# Deliberately conservative and short: false positives (blocking a
# borderline-fine sentence) are cheap to work around by rephrasing;
# false negatives (letting real compliance-framing language through)
# are the actual risk this guards against. Extend this list rather than
# narrowing it if something slips through in practice.
BANNED_TERMS = [
    r"\bAML\b",
    r"anti-money laundering",
    r"\bKYC\b",
    r"know your customer",
    r"sanctions? (list|screening|check)",
    r"OFAC",
    r"risk score",
    r"risk rating",
    r"fraud (score|risk|detection)",
    r"compliance (check|flag|status)",
    r"money laundering",
    r"suspicious activity",
    r"watchlist",
]

_PATTERN = re.compile("|".join(BANNED_TERMS), re.IGNORECASE)


class NeutralLanguageViolation(Exception):
    """Raised when text fails the neutral-language check. Callers should
    treat this as a hard stop, not a warning -- see assert_neutral_language."""

    def __init__(self, text: str, matched_terms: list[str]):
        self.text = text
        self.matched_terms = matched_terms
        super().__init__(
            f"Text contains {len(matched_terms)} compliance/risk-framing term(s) "
            f"not allowed in ChainLedgerAI output: {matched_terms}"
        )


def find_violations(text: str) -> list[str]:
    """Returns the list of matched banned terms/phrases, empty if clean."""
    return sorted({m.group(0) for m in _PATTERN.finditer(text)})


def assert_neutral_language(text: str) -> str:
    """Raises NeutralLanguageViolation if text contains any banned
    compliance/risk-framing language; returns the text unchanged if
    clean. Call this on every piece of AI-generated or templated text
    before it leaves chainledger_api -- see main.py's /summarize route."""
    violations = find_violations(text)
    if violations:
        raise NeutralLanguageViolation(text, violations)
    return text
