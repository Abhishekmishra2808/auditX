"""
Integration tests for the full FinancialMappingPipeline.
"""

from __future__ import annotations

import logging

import pytest

from financial_mapper.config import (
    MatchingConfig,
    PipelineConfig,
    ValidationConfig,
)
from financial_mapper.pipeline import FinancialMappingPipeline


@pytest.fixture
def pipeline() -> FinancialMappingPipeline:
    return FinancialMappingPipeline(
        config=PipelineConfig(
            matching=MatchingConfig(
                fuzzy_threshold=75.0,
                strict_mode=False,
            ),
            validation=ValidationConfig(error_on_duplicate=False),
            log_level=logging.WARNING,
        )
    )


@pytest.fixture
def strict_pipeline() -> FinancialMappingPipeline:
    return FinancialMappingPipeline(
        config=PipelineConfig(
            matching=MatchingConfig(
                fuzzy_threshold=75.0,
                strict_mode=True,
            ),
            validation=ValidationConfig(
                required_fields=["Net Profit", "Current Assets"],
                error_on_duplicate=True,
            ),
            log_level=logging.WARNING,
        )
    )


# ======================================================================
# Basic mapping
# ======================================================================

class TestBasicMapping:
    def test_synonym_mapping(self, pipeline: FinancialMappingPipeline) -> None:
        result = pipeline.map_dict({"Profit After Tax": 500_000})
        assert result.success
        assert len(result.mappings) == 1
        m = result.mappings[0]
        assert m.canonical_name == "Net Profit"
        assert m.value == 500_000.0
        assert m.confidence == 100.0
        assert m.match_method == "synonym"

    def test_multiple_synonyms(self, pipeline: FinancialMappingPipeline) -> None:
        result = pipeline.map_dict({
            "Profit After Tax": 500_000,
            "Owner Funds": 1_200_000,
        })
        mapped = result.mapped_dict()
        assert mapped["Net Profit"] == 500_000.0
        assert mapped["Net Worth"] == 1_200_000.0

    def test_fuzzy_mapping(self, pipeline: FinancialMappingPipeline) -> None:
        result = pipeline.map_dict({"Nett Proffit": 100_000})
        assert len(result.mappings) >= 1
        # The fuzzy matcher should find "Net Profit"
        names = [m.canonical_name for m in result.mappings]
        assert "Net Profit" in names

    def test_unmapped_label(self, pipeline: FinancialMappingPipeline) -> None:
        result = pipeline.map_dict({"Completely Unknown XYZ": 999})
        assert len(result.unmapped) == 1
        assert result.unmapped[0]["raw_label"] == "Completely Unknown XYZ"


# ======================================================================
# Value handling
# ======================================================================

class TestValueHandling:
    def test_string_value_with_commas(
        self, pipeline: FinancialMappingPipeline
    ) -> None:
        result = pipeline.map_dict({"Net Sales": "4,200,000"})
        assert result.mappings[0].value == 4_200_000.0

    def test_parenthetical_negative(
        self, pipeline: FinancialMappingPipeline
    ) -> None:
        result = pipeline.map_dict({"Net Profit": "(50000)"})
        assert result.mappings[0].value == -50_000.0

    def test_currency_prefix(self, pipeline: FinancialMappingPipeline) -> None:
        result = pipeline.map_dict({"Net Sales": "₹1,00,000"})
        assert result.mappings[0].value == 100_000.0


# ======================================================================
# Strict mode
# ======================================================================

class TestStrictMode:
    def test_strict_mode_raises_on_missing(
        self, strict_pipeline: FinancialMappingPipeline
    ) -> None:
        with pytest.raises(RuntimeError, match="Strict mode"):
            strict_pipeline.map_dict({"Net Profit": 100_000})
            # "Current Assets" missing → error

    def test_strict_mode_passes(
        self, strict_pipeline: FinancialMappingPipeline
    ) -> None:
        result = strict_pipeline.map_dict({
            "Net Profit": 100_000,
            "Current Assets": 200_000,
        })
        assert result.success


# ======================================================================
# CSV input
# ======================================================================

class TestCsvInput:
    def test_csv_string(self, pipeline: FinancialMappingPipeline) -> None:
        csv_text = "Label,Value\nNet Sales,4200000\nNet Profit,500000\n"
        result = pipeline.map_csv(csv_text)
        mapped = result.mapped_dict()
        assert "Net Sales" in mapped
        assert "Net Profit" in mapped


# ======================================================================
# JSON input
# ======================================================================

class TestJsonInput:
    def test_json_string(self, pipeline: FinancialMappingPipeline) -> None:
        import json

        raw = json.dumps({"Net Sales": 4_200_000, "Net Profit": 500_000})
        result = pipeline.map_json(raw)
        mapped = result.mapped_dict()
        assert mapped["Net Sales"] == 4_200_000.0
        assert mapped["Net Profit"] == 500_000.0


# ======================================================================
# Hot-add synonyms
# ======================================================================

class TestHotAddSynonyms:
    def test_add_synonym_after_init(
        self, pipeline: FinancialMappingPipeline
    ) -> None:
        # Initially unmapped
        r1 = pipeline.map_dict({"My Custom Field": 42})
        assert len(r1.unmapped) == 1

        # Add synonym
        pipeline.add_synonyms({"My Custom Field": "Revenue"})

        # Now maps
        r2 = pipeline.map_dict({"My Custom Field": 42})
        assert len(r2.mappings) == 1
        assert r2.mappings[0].canonical_name == "Revenue"


# ======================================================================
# Audit trail
# ======================================================================

class TestAuditTrail:
    def test_output_contains_all_fields(
        self, pipeline: FinancialMappingPipeline
    ) -> None:
        result = pipeline.map_dict({"Net Sales": 1000})
        d = result.to_dict()
        assert "mappings" in d
        assert "unmapped" in d
        assert "validation_errors" in d
        assert "validation_warnings" in d
        assert "success" in d

        m = d["mappings"][0]
        assert "canonical_name" in m
        assert "raw_label" in m
        assert "value" in m
        assert "confidence" in m
        assert "match_method" in m
        assert "warnings" in m
