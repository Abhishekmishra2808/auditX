"""Validation checks for canonical mapped datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from financial_mapper.logging_setup import get_logger

logger = get_logger("validation")

BALANCE_MISMATCH_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ValidationConfigSimple:
    """Simple validation configuration for canonical dataset checks."""

    mismatch_tolerance: float = BALANCE_MISMATCH_TOLERANCE


class CanonicalValidator:
    """Validator for canonical mapped values used by ratio engine."""

    def __init__(self, config: Optional[ValidationConfigSimple] = None) -> None:
        self.config = config or ValidationConfigSimple()

    def validate(self, canonical_dataset: Dict[str, Dict[str, float]]) -> List[str]:
        """Validate total asset/liability consistency and return warnings."""
        warnings: List[str] = []
        assets_payload = canonical_dataset.get("total_assets")
        liabilities_payload = canonical_dataset.get("total_liabilities")

        if assets_payload is None or liabilities_payload is None:
            return warnings

        total_assets = float(assets_payload.get("value", 0.0))
        total_liabilities = float(liabilities_payload.get("value", 0.0))
        mismatch = abs(total_assets - total_liabilities)

        if mismatch > self.config.mismatch_tolerance:
            message = (
                "Balance mismatch detected: total_assets="
                f"{total_assets}, total_liabilities={total_liabilities}, "
                f"delta={mismatch}"
            )
            warnings.append(message)
            logger.warning(message)

        return warnings
