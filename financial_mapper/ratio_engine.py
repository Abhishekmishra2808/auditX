"""Deterministic ratio engine using canonical mapped dataset only."""

from __future__ import annotations

import math
from typing import Dict, Optional

CURRENT_ASSETS_KEY = "current_assets"
CURRENT_LIABILITIES_KEY = "current_liabilities"
CASH_KEY = "cash"
RECEIVABLES_KEY = "receivables"
TOTAL_LIABILITIES_KEY = "total_liabilities"
EQUITY_KEY = "equity"


class RatioEngine:
    """Compute core ratios without any LLM dependency."""

    @staticmethod
    def _safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator is None or denominator == 0:
            return None
        result = numerator / denominator
        if math.isnan(result) or math.isinf(result):
            return None
        return result

    @staticmethod
    def _get_value(canonical_dataset: Dict[str, Dict[str, float]], key: str) -> Optional[float]:
        payload = canonical_dataset.get(key)
        if payload is None:
            return None
        value = payload.get("value")
        if value is None:
            return None
        return float(value)

    def calculate(self, canonical_dataset: Dict[str, Dict[str, float]]) -> Dict[str, Optional[float]]:
        """Calculate current ratio, quick ratio, and debt-to-equity."""
        current_assets = self._get_value(canonical_dataset, CURRENT_ASSETS_KEY)
        current_liabilities = self._get_value(canonical_dataset, CURRENT_LIABILITIES_KEY)
        cash = self._get_value(canonical_dataset, CASH_KEY)
        receivables = self._get_value(canonical_dataset, RECEIVABLES_KEY)
        total_liabilities = self._get_value(canonical_dataset, TOTAL_LIABILITIES_KEY)
        equity = self._get_value(canonical_dataset, EQUITY_KEY)

        quick_assets: Optional[float] = None
        if cash is not None or receivables is not None:
            quick_assets = (cash or 0.0) + (receivables or 0.0)

        return {
            "current_ratio": self._safe_divide(current_assets, current_liabilities),
            "quick_ratio": self._safe_divide(quick_assets, current_liabilities),
            "debt_to_equity": self._safe_divide(total_liabilities, equity),
        }
