"""
Unit tests for the LabelNormalizer.
"""

from __future__ import annotations

import pytest

from financial_mapper.normalizer import LabelNormalizer


@pytest.fixture
def normalizer() -> LabelNormalizer:
    return LabelNormalizer()


# ======================================================================
# Label normalisation
# ======================================================================

class TestNormalizeLabel:
    def test_lowercase_and_strip(self, normalizer: LabelNormalizer) -> None:
        assert normalizer.normalize_label("  Profit After Tax  ") == "profit after tax"

    def test_punctuation_removal(self, normalizer: LabelNormalizer) -> None:
        result = normalizer.normalize_label("Reserves & Surplus (Total)")
        # '&' is kept; parentheses are stripped
        assert "&" in result
        assert "(" not in result
        assert ")" not in result

    def test_unicode_dash_normalised(self, normalizer: LabelNormalizer) -> None:
        assert normalizer.normalize_label("Long–term Borrowings") == "long-term borrowings"
        assert normalizer.normalize_label("Long—term Borrowings") == "long-term borrowings"

    def test_whitespace_collapse(self, normalizer: LabelNormalizer) -> None:
        assert normalizer.normalize_label("Net   Sales") == "net sales"

    def test_empty_string(self, normalizer: LabelNormalizer) -> None:
        assert normalizer.normalize_label("") == ""

    def test_numbers_preserved(self, normalizer: LabelNormalizer) -> None:
        result = normalizer.normalize_label("FY2024 Sales")
        assert "2024" in result


# ======================================================================
# Value normalisation
# ======================================================================

class TestNormalizeValue:
    def test_integer_passthrough(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value(500000)
        assert val == 500000.0
        assert warns == []

    def test_float_passthrough(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value(3.14)
        assert val == 3.14
        assert warns == []

    def test_string_with_commas(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("1,23,456")
        assert val == 123456.0

    def test_currency_prefix(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("₹12,000")
        assert val == 12000.0

    def test_parenthetical_negative(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("(5000)")
        assert val == -5000.0

    def test_percent_stripped(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("12.5%")
        assert val == 12.5
        assert any("Percent" in w for w in warns)

    def test_none_value(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value(None)
        assert val is None
        assert len(warns) == 1

    def test_empty_string(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("")
        assert val is None

    def test_non_numeric_string(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("N/A")
        assert val is None
        assert any("Cannot parse" in w for w in warns)

    def test_dollar_prefix(self, normalizer: LabelNormalizer) -> None:
        val, warns = normalizer.normalize_value("$1,000")
        assert val == 1000.0


# ======================================================================
# Pair normalisation
# ======================================================================

class TestNormalizePair:
    def test_basic(self, normalizer: LabelNormalizer) -> None:
        label, value, warns = normalizer.normalize_pair("Net Sales", "4,200,000")
        assert label == "net sales"
        assert value == 4200000.0
        assert warns == []
