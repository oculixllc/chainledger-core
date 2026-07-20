import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chainledger_core.guardrails import NeutralLanguageViolation, assert_neutral_language, find_violations


@pytest.mark.parametrize("clean_text", [
    "This address had 42 transactions in the last 30 days across 11 counterparties.",
    "High-frequency wallet with 3.2 ETH in total inbound volume.",
    "First activity 180 days ago, most recent activity 2 hours ago.",
    "This contract implements the ERC-20 interface.",
])
def test_neutral_text_passes_unchanged(clean_text):
    assert assert_neutral_language(clean_text) == clean_text
    assert find_violations(clean_text) == []


@pytest.mark.parametrize("banned_text,expected_term", [
    ("This wallet shows signs of potential money laundering.", "money laundering"),
    ("Flagged for AML review before proceeding.", "AML"),
    ("Recommend a KYC check on this counterparty.", "KYC"),
    ("This address appears on a sanctions list.", "sanctions list"),
    ("Risk score: 87/100, high risk.", "risk score"),
    ("Possible OFAC match detected.", "OFAC"),
    ("This transaction pattern suggests suspicious activity.", "suspicious activity"),
])
def test_banned_language_is_caught(banned_text, expected_term):
    violations = find_violations(banned_text)
    assert len(violations) >= 1
    with pytest.raises(NeutralLanguageViolation) as exc_info:
        assert_neutral_language(banned_text)
    assert expected_term.lower() in [v.lower() for v in exc_info.value.matched_terms]


def test_case_insensitive_matching():
    assert find_violations("this is about ANTI-MONEY LAUNDERING") != []
    assert find_violations("kyc verification needed") != []


def test_violation_exception_carries_original_text_and_matches():
    with pytest.raises(NeutralLanguageViolation) as exc_info:
        assert_neutral_language("Flagged for AML and KYC review.")
    assert exc_info.value.text == "Flagged for AML and KYC review."
    assert len(exc_info.value.matched_terms) == 2
