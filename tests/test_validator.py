"""
Unit tests for the Validator.
"""

from __future__ import annotations

import math

import pytest

from financial_mapper.config import ValidationConfig
from financial_mapper.schema import MappingResult
from financial_mapper.validator import Validator


def _make_result(
    canonical: str = "Net Profit",
    raw: str = "PAT",
    value: float = 100_000,
    **kwargs,
) -> MappingResult:
    return MappingResult(
        canonical_name=canonical,
        raw_label=raw,
        value=value,
        confidence=100.0,
        match_method="synonym",
        **kwargs,
    )


@pytest.fixture
def validator() -> Validator:
    return Validator(config=ValidationConfig())


@pytest.fixture
def strict_validator() -> Validator:
    return Validator(config=ValidationConfig(
        required_fields=["Net Profit", "Current Assets"],
        error_on_duplicate=True,
    ))


# ======================================================================
# Duplicate detection
# ======================================================================

class TestDuplicates:
    def test_no_duplicates_clean(self, validator: Validator) -> None:
        mappings = [
            _make_result("Net Profit", "PAT", 100_000),
            _make_result("Current Assets", "CA", 200_000),
        ]
        report = validator.validate(mappings)
        assert report.is_valid

    def test_duplicate_detected(self, validator: Validator) -> None:
        mappings = [
            _make_result("Net Profit", "PAT", 100_000),
            _make_result("Net Profit", "Profit After Tax", 100_000),
        ]
        report = validator.validate(mappings)
        assert not report.is_valid  # error_on_duplicate defaults True

    def test_duplicate_warning_mode(self) -> None:
        v = Validator(config=ValidationConfig(error_on_duplicate=False))
        mappings = [
            _make_result("Net Profit", "PAT", 100_000),
            _make_result("Net Profit", "Profit After Tax", 100_000),
        ]
        report = v.validate(mappings)
        assert report.is_valid  # only warnings
        assert len(report.warnings) >= 1


# ======================================================================
# Required fields
# ======================================================================

class TestRequiredFields:
    def test_all_present(self, strict_validator: Validator) -> None:
        mappings = [
            _make_result("Net Profit", "PAT", 100_000),
            _make_result("Current Assets", "CA", 200_000),
        ]
        report = strict_validator.validate(mappings)
        assert report.is_valid

    def test_missing_required(self, strict_validator: Validator) -> None:
        mappings = [
            _make_result("Net Profit", "PAT", 100_000),
        ]
        report = strict_validator.validate(mappings)
        assert not report.is_valid
        assert any("Current Assets" in e for e in report.errors)


# ======================================================================
# Value sanity
# ======================================================================

class TestValues:
    def test_none_value_warning(self, validator: Validator) -> None:
        mappings = [_make_result(value=None)]
        report = validator.validate(mappings)
        assert len(report.warnings) >= 1

    def test_nan_value_error(self, validator: Validator) -> None:
        mappings = [_make_result(value=float("nan"))]
        report = validator.validate(mappings)
        assert not report.is_valid

    def test_inf_value_error(self, validator: Validator) -> None:
        mappings = [_make_result(value=math.inf)]
        report = validator.validate(mappings)
        assert not report.is_valid

    def test_huge_value_warning(self, validator: Validator) -> None:
        mappings = [_make_result(value=9e15)]
        report = validator.validate(mappings)
        assert len(report.warnings) >= 1
