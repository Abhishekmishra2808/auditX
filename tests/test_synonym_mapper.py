"""
Unit tests for the SynonymMapper.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from financial_mapper.normalizer import LabelNormalizer
from financial_mapper.synonym_mapper import SynonymMapper


@pytest.fixture
def normalizer() -> LabelNormalizer:
    return LabelNormalizer()


@pytest.fixture
def mapper(normalizer: LabelNormalizer) -> SynonymMapper:
    return SynonymMapper(normalizer=normalizer)


# ======================================================================
# Core lookup
# ======================================================================

class TestLookup:
    def test_exact_normalised_hit(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("profit after tax") == "Net Profit"

    def test_abbreviation_hit(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("pat") == "Net Profit"

    def test_miss_returns_none(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("completely unknown field") is None

    def test_current_liabilities_variants(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("current liabilities") == "Current Liabilities"
        assert mapper.lookup("total current liabilities") == "Current Liabilities"

    def test_owners_funds(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("owners funds") == "Net Worth"
        assert mapper.lookup("shareholders funds") == "Net Worth"

    def test_opening_stock(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("opening stock") == "Opening Inventory"

    def test_closing_stock(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("closing stock") == "Closing Inventory"

    def test_interest_variants(self, mapper: SynonymMapper) -> None:
        assert mapper.lookup("interest expense") == "Interest"
        assert mapper.lookup("finance cost") == "Interest"
        assert mapper.lookup("finance costs") == "Interest"


# ======================================================================
# Extension API
# ======================================================================

class TestExtension:
    def test_add_single_synonym(
        self, mapper: SynonymMapper, normalizer: LabelNormalizer
    ) -> None:
        mapper.add_synonym("My Custom Label", "Net Profit")
        norm = normalizer.normalize_label("My Custom Label")
        assert mapper.lookup(norm) == "Net Profit"

    def test_add_invalid_canonical_raises(self, mapper: SynonymMapper) -> None:
        with pytest.raises(ValueError, match="Unknown canonical name"):
            mapper.add_synonym("foo", "Not A Real Field")

    def test_bulk_add(
        self, mapper: SynonymMapper, normalizer: LabelNormalizer
    ) -> None:
        mapper.add_synonyms({
            "custom a": "Revenue",
            "custom b": "Tax",
        })
        assert mapper.lookup("custom a") == "Revenue"
        assert mapper.lookup("custom b") == "Tax"

    def test_load_from_json_file(
        self, mapper: SynonymMapper, normalizer: LabelNormalizer
    ) -> None:
        data = {"json loaded label": "Net Worth"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        count = mapper.load_custom_synonyms(path)
        assert count == 1
        norm = normalizer.normalize_label("json loaded label")
        assert mapper.lookup(norm) == "Net Worth"

        path.unlink()


# ======================================================================
# Introspection
# ======================================================================

class TestIntrospection:
    def test_size_positive(self, mapper: SynonymMapper) -> None:
        assert mapper.size > 100  # built-in dict has ~200 entries

    def test_all_synonyms_returns_copy(self, mapper: SynonymMapper) -> None:
        d = mapper.all_synonyms()
        original_size = mapper.size
        d["injected"] = "Net Profit"
        assert mapper.size == original_size  # original unchanged
