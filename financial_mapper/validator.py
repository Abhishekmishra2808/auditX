"""
Validation Layer.

Post-mapping validation that checks the quality and completeness of the
pipeline output *before* it is handed to downstream consumers.

Checks performed
----------------
1. **Required fields** — configurable list of canonical fields that must be
   present; missing ones produce validation errors.
2. **Numeric sanity** — values must be finite and within a plausible range.
3. **Duplicate detection** — the same canonical name must not be mapped twice.
4. **Value warnings** — ``None`` values, suspiciously round numbers, etc.
"""

from __future__ import annotations

import math
from typing import List

from financial_mapper.config import ValidationConfig
from financial_mapper.logging_setup import get_logger
from financial_mapper.schema import MappingResult

logger = get_logger("validator")


class ValidationReport:
    """Accumulates errors and warnings during a validation pass."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        logger.error("Validation ERROR: %s", msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("Validation WARNING: %s", msg)


class Validator:
    """Validates a list of ``MappingResult`` objects.

    Parameters
    ----------
    config:
        Validation thresholds and behaviour flags.
    """

    def __init__(self, config: ValidationConfig) -> None:
        self._config = config

    def validate(self, mappings: List[MappingResult]) -> ValidationReport:
        """Run all checks and return a ``ValidationReport``."""
        report = ValidationReport()
        self._check_duplicates(mappings, report)
        self._check_required_fields(mappings, report)
        self._check_values(mappings, report)
        return report

    # ------------------------------------------------------------------ #
    # Individual checks
    # ------------------------------------------------------------------ #

    def _check_duplicates(
        self, mappings: List[MappingResult], report: ValidationReport
    ) -> None:
        """Detect if two raw labels mapped to the same canonical name."""
        seen: dict[str, str] = {}  # canonical → first raw_label
        for m in mappings:
            if m.canonical_name in seen:
                msg = (
                    f"Duplicate canonical mapping '{m.canonical_name}': "
                    f"first from '{seen[m.canonical_name]}', "
                    f"again from '{m.raw_label}'"
                )
                if self._config.error_on_duplicate:
                    report.add_error(msg)
                else:
                    report.add_warning(msg)
            else:
                seen[m.canonical_name] = m.raw_label

    def _check_required_fields(
        self, mappings: List[MappingResult], report: ValidationReport
    ) -> None:
        """Ensure every required canonical field has a mapping."""
        if not self._config.required_fields:
            return

        mapped_names = {m.canonical_name for m in mappings}
        for req in self._config.required_fields:
            if req not in mapped_names:
                report.add_error(f"Required field missing: '{req}'")

    def _check_values(
        self, mappings: List[MappingResult], report: ValidationReport
    ) -> None:
        """Sanity-check individual values."""
        for m in mappings:
            if m.value is None:
                report.add_warning(
                    f"'{m.canonical_name}' (from '{m.raw_label}') has value None"
                )
                continue

            if not isinstance(m.value, (int, float)):
                report.add_warning(
                    f"'{m.canonical_name}' has non-numeric value: {m.value!r}"
                )
                continue

            if math.isnan(m.value) or math.isinf(m.value):
                report.add_error(
                    f"'{m.canonical_name}' has non-finite value: {m.value}"
                )
                continue

            if abs(m.value) > self._config.max_absolute_value:
                report.add_warning(
                    f"'{m.canonical_name}' value {m.value} exceeds "
                    f"max_absolute_value ({self._config.max_absolute_value}). "
                    f"Possible unit error?"
                )
