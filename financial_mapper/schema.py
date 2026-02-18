"""
Canonical financial schema and data models.

Defines the target schema (the "truth" that raw labels are mapped into)
and the typed data structures carried through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Canonical Schema
# ---------------------------------------------------------------------------

class CanonicalField(str, Enum):
    """
    Every field the system can map to.

    Using an enum prevents typos and makes downstream comparisons safe.
    The ``.value`` is the human-readable canonical name.
    """

    CURRENT_ASSETS = "Current Assets"
    CURRENT_LIABILITIES = "Current Liabilities"
    LONG_TERM_BORROWINGS = "Long-term Borrowings"
    LONG_TERM_PROVISIONS = "Long-term Provisions"
    SHARE_CAPITAL = "Share Capital"
    RESERVES_AND_SURPLUS = "Reserves & Surplus"
    GROSS_PROFIT = "Gross Profit"
    INDIRECT_EXPENSES = "Indirect Expenses"
    CASH_SALES = "Cash Sales"
    CREDIT_SALES = "Credit Sales"
    OTHER_OPERATING_INCOME = "Other Operating Income"
    OPERATING_EXPENSES = "Operating Expenses"
    CASH_ACCRUALS = "Cash Accruals"
    LOAN_INSTALLMENT = "Loan Installment"
    INTEREST = "Interest"
    OPENING_INVENTORY = "Opening Inventory"
    CLOSING_INVENTORY = "Closing Inventory"
    NET_PURCHASES = "Net Purchases"
    DIRECT_EXPENSES = "Direct Expenses"
    OPENING_DEBTORS = "Opening Debtors"
    CLOSING_DEBTORS = "Closing Debtors"
    NET_SALES = "Net Sales"
    LONG_TERM_LIABILITIES = "Long-term Liabilities"
    INTANGIBLE_ASSETS = "Intangible Assets"
    FIXED_COST = "Fixed Cost"
    SELLING_PRICE = "Selling Price"
    VARIABLE_COST = "Variable Cost"

    # Extended — commonly derived / needed for ratio calculations
    NET_PROFIT = "Net Profit"
    NET_WORTH = "Net Worth"
    TOTAL_ASSETS = "Total Assets"
    TOTAL_LIABILITIES = "Total Liabilities"
    EBITDA = "EBITDA"
    DEPRECIATION = "Depreciation"
    TAX = "Tax"
    REVENUE = "Revenue"
    TOTAL_DEBT = "Total Debt"
    EQUITY = "Equity"
    WORKING_CAPITAL = "Working Capital"
    TANGIBLE_ASSETS = "Tangible Assets"
    FIXED_ASSETS = "Fixed Assets"
    INVENTORY = "Inventory"
    TRADE_RECEIVABLES = "Trade Receivables"
    TRADE_PAYABLES = "Trade Payables"
    CASH_AND_EQUIVALENTS = "Cash and Cash Equivalents"
    TOTAL_INCOME = "Total Income"
    TOTAL_EXPENSES = "Total Expenses"
    NET_REVENUE = "Net Revenue"
    COST_OF_GOODS_SOLD = "Cost of Goods Sold"
    OPERATING_PROFIT = "Operating Profit"
    PROFIT_BEFORE_TAX = "Profit Before Tax"


# Convenience set for quick membership tests
CANONICAL_NAMES: set[str] = {f.value for f in CanonicalField}


def canonical_lookup(name: str) -> Optional[CanonicalField]:
    """Case-insensitive lookup by value."""
    _lower = name.strip().lower()
    for f in CanonicalField:
        if f.value.lower() == _lower:
            return f
    return None


# ---------------------------------------------------------------------------
# Pipeline Data Models
# ---------------------------------------------------------------------------

@dataclass
class MappingResult:
    """A single raw-label → canonical-field mapping produced by the pipeline."""

    canonical_name: str
    raw_label: str
    value: Any
    confidence: float  # 0.0 – 100.0
    match_method: str  # "synonym" | "fuzzy" | "semantic" | "exact"
    warnings: list[str] = field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        return len(self.warnings) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "raw_label": self.raw_label,
            "value": self.value,
            "confidence": round(self.confidence, 2),
            "match_method": self.match_method,
            "warnings": self.warnings,
        }


@dataclass
class PipelineOutput:
    """Aggregate result of a full pipeline run."""

    mappings: list[MappingResult] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.validation_errors) == 0

    def mapped_dict(self) -> dict[str, Any]:
        """Return {canonical_name: value} for all confident mappings."""
        return {m.canonical_name: m.value for m in self.mappings}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "mappings": [m.to_dict() for m in self.mappings],
            "unmapped": self.unmapped,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
        }
