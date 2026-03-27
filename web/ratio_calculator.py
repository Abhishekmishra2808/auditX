"""Compatibility wrapper around the deterministic ratio engine."""

from __future__ import annotations

from typing import Any, Dict

from financial_mapper.ratio_engine import RatioEngine


class RatioCalculator:
    """Calculate core ratios from canonical mapped values only."""

    def __init__(self) -> None:
        self._engine = RatioEngine()

    def calculate_all_ratios(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Return ratio results in UI-compatible grouped format."""
        canonical_dataset = self._to_canonical_dataset(data)
        computed = self._engine.calculate(canonical_dataset)

        grouped = {
            "Liquidity Ratios": {
                "Current Ratio": {
                    "value": computed.get("current_ratio"),
                    "formula": "current_assets / current_liabilities",
                },
                "Quick Ratio": {
                    "value": computed.get("quick_ratio"),
                    "formula": "(cash + receivables) / current_liabilities",
                },
            },
            "Solvency Ratios": {
                "Debt-to-Equity Ratio": {
                    "value": computed.get("debt_to_equity"),
                    "formula": "total_liabilities / equity",
                },
            },
        }

        return {
            category: {
                ratio_name: payload
                for ratio_name, payload in category_values.items()
                if payload.get("value") is not None
            }
            for category, category_values in grouped.items()
            if any(payload.get("value") is not None for payload in category_values.values())
        }

    @staticmethod
    def _to_canonical_dataset(data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Accept plain numeric dicts and normalize to canonical payload format."""
        converted: Dict[str, Dict[str, float]] = {}
        for key, value in data.items():
            if isinstance(value, dict) and "value" in value:
                converted[key] = {"value": float(value["value"]), "confidence": float(value.get("confidence", 1.0))}
            elif isinstance(value, (int, float)):
                converted[key] = {"value": float(value), "confidence": 1.0}
        return converted
