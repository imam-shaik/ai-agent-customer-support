"""Demo-mode query correction tests (8b-7).

The corrector is the demo-mode analog of the live pipeline's spelling
correction (assessment model 8b-2): deterministic, conservative, corpus-
anchored. These tests pin the exact rule — unique near-match only, same
first letter, small edit budget, short filler tokens never touched.
"""

from __future__ import annotations

import pytest

from app.services.query_correction import correct_spelling

_VOCABULARY = frozenset(
    {
        # corpus words (as the billing/access knowledge base would contain)
        "billed",
        "billing",
        "bill",
        "invoice",
        "invoices",
        "password",
        "reset",
        "invite",
        "team",
        "members",
        "subscription",
        "monthly",
        "annually",
        "the",
        "when",
        "how",
        "passwords",
    }
)


class TestCorrectSpelling:
    def test_corrects_single_misspelling_to_unique_match(self):
        assert correct_spelling("when am i billled?", _VOCABULARY) == (
            "when am i billed?"
        )

    def test_corrects_doubled_letter_and_dropped_letter(self):
        assert correct_spelling("resset password", _VOCABULARY) == (
            "reset password"
        )
        assert correct_spelling("passwod reset", _VOCABULARY) == (
            "password reset"
        )

    def test_correct_word_in_vocabulary_stays_untouched(self):
        assert correct_spelling("when am I billed?", _VOCABULARY) == (
            "when am I billed?"
        )

    def test_short_tokens_are_never_corrected(self):
        # Greetings, filler and pronouns stay as typed — "hi" must never
        # morph into a corpus word and break small-talk classification.
        assert correct_spelling("hi ok i am her", _VOCABULARY) == (
            "hi ok i am her"
        )

    def test_ambiguous_near_match_is_kept_as_typed(self):
        # "invoicez" sits at distance 1 from BOTH "invoice" (drop "z") and
        # "invoices" (z→s): a tie means the intended word is ambiguous —
        # never guess, keep the customer's word.
        assert correct_spelling("my invoicez", _VOCABULARY) == "my invoicez"

    def test_unknown_word_without_near_match_is_kept(self):
        assert correct_spelling("what is a flurbnik?", _VOCABULARY) == (
            "what is a flurbnik?"
        )

    def test_first_letter_must_match(self):
        # "resset" → "reset" (same first letter). A word whose nearest
        # corpus neighbor starts differently must stay untouched.
        assert correct_spelling("aeset the team", _VOCABULARY) == (
            "aeset the team"
        )

    def test_punctuation_spacing_and_case_are_preserved(self):
        assert correct_spelling("Hello! When am i billled?", _VOCABULARY) == (
            "Hello! When am i billed?"
        )

    def test_empty_text_and_empty_vocabulary_are_safe(self):
        assert correct_spelling("", _VOCABULARY) == ""
        assert correct_spelling("when am i billled?", frozenset()) == (
            "when am i billled?"
        )

    def test_long_word_budget_is_two_edits(self):
        # "subscrption" (dropped "i") is distance 1 from "subscription".
        assert correct_spelling("my subscrption", _VOCABULARY) == (
            "my subscription"
        )
        # Distance 3 is over ANY budget: kept as typed.
        assert correct_spelling("subxxxxxxxxxx", _VOCABULARY) == (
            "subxxxxxxxxxx"
        )

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("when am i billled?", "when am i billed?"),
            ("hw do i invte my tream?", "hw do i invite my team?"),
        ],
    )
    def test_documented_demo_failures_now_correct(self, text, expected):
        assert correct_spelling(text, _VOCABULARY) == expected
