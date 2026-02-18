"""
Unit tests for the FuzzyMatcher.
"""

from __future__ import annotations

import pytest

from financial_mapper.config import MatchingConfig
from financial_mapper.fuzzy_matcher import FuzzyMatcher


@pytest.fixture
def matcher() -> FuzzyMatcher:
    return FuzzyMatcher(config=MatchingConfig(fuzzy_threshold=75.0))


@pytest.fixture
def strict_matcher() -> FuzzyMatcher:
    return FuzzyMatcher(config=MatchingConfig(fuzzy_threshold=90.0))


# ======================================================================
# Matching
# ======================================================================

class TestMatch:
    def test_close_match_accepted(self, matcher: FuzzyMatcher) -> None:
        result = matcher.match("net profiit")  # small typo
        assert result is not None
        assert result.canonical_name == "Net Profit"
        assert result.score >= 75.0

    def test_exact_canonical_name(self, matcher: FuzzyMatcher) -> None:
        result = matcher.match("current assets")
        assert result is not None
        assert result.canonical_name == "Current Assets"
        assert result.score >= 90.0

    def test_no_match_below_threshold(self, strict_matcher: FuzzyMatcher) -> None:
        result = strict_matcher.match("xyzzy gibberish")
        assert result is None

    def test_word_order_insensitive(self, matcher: FuzzyMatcher) -> None:
        result = matcher.match("profit net")
        assert result is not None
        assert result.canonical_name == "Net Profit"

    def test_empty_input(self, matcher: FuzzyMatcher) -> None:
        result = matcher.match("")
        assert result is None


# ======================================================================
# Batch matching
# ======================================================================

class TestBatch:
    def test_batch_returns_dict(self, matcher: FuzzyMatcher) -> None:
        labels = ["net profit", "current assets", "nonsense blob"]
        results = matcher.match_batch(labels)
        assert isinstance(results, dict)
        assert len(results) == 3
        assert results["net profit"] is not None
        assert results["current assets"] is not None
