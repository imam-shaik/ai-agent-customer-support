"""Shared text normalization (Phase 8B).

One deterministic normalization for "material words", used by BOTH the
coverage gate (evidence sufficiency signal B) and the stub provider, so
they judge vocabulary identically. Deliberately crude — lowercase, light
suffix stripping, stopword removal — never fuzzy matching that could hide
a mismatch between question and evidence.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9']+")

# Non-discriminative words: greetings, grammar, politeness. A shared
# stopword must never make evidence look relevant or citable.
STOPWORDS = frozenset(
    """
    a an the and or but if then else than too very just also
    i me my mine we our us you your yours he him his she her hers it its
    they them their this that these those there here
    is are was were be been being am do does did doing done
    can could shall should will would may might must
    have has had having
    of in on at to from by for with about into over under after before
    up down out off again further once
    what when where why who whom which how whose
    not no nor so as
    hello hi hey yo good morning afternoon evening please thanks thank
    sure okay ok yeah yes something anything anyone everyone
    help helping need needs needed want wants
    get gets got make makes made use uses using
    """
    .split()
)


def significant_words(text: str) -> set[str]:
    """Lowercased tokens with light suffix stripping, minus stopwords.

    The crude normalization (ing/ed/s) lets "billed" match "billing" and
    "seats" match "seat" — deterministic heuristics only.
    """
    words: set[str] = set()
    for token in _WORD_RE.findall((text or "").lower()):
        if len(token) <= 2:
            continue
        word = token
        if len(word) > 4:
            for suffix in ("ing", "ed", "s"):
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    word = word[: -len(suffix)]
                    break
        if word in STOPWORDS:
            continue
        words.add(word)
    return words
