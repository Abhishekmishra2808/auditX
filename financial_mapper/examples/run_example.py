#!/usr/bin/env python3
"""
Example: Financial Mapping Pipeline Demo.

Demonstrates all three input formats (dict, CSV, JSON) and prints
the full auditable output.

Run from the project root:
    python -m financial_mapper.examples.run_example
or:
    python financial_mapper/examples/run_example.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from financial_mapper.config import (
    MatchingConfig,
    PipelineConfig,
    ValidationConfig,
)
from financial_mapper.pipeline import FinancialMappingPipeline


# ======================================================================
# Helper
# ======================================================================

def print_section(title: str) -> None:
    width = 72
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_output(output) -> None:  # noqa: ANN001
    """Pretty-print a PipelineOutput."""
    d = output.to_dict()
    print(json.dumps(d, indent=2, ensure_ascii=False))
    print(f"\n  ✓ Mapped fields : {len(output.mappings)}")
    print(f"  ✗ Unmapped      : {len(output.unmapped)}")
    print(f"  ⚠ Warnings      : {len(output.validation_warnings)}")
    print(f"  ✖ Errors        : {len(output.validation_errors)}")
    print(f"  Success         : {output.success}")


# ======================================================================
# Demo 1 — Dictionary input
# ======================================================================

def demo_dict(pipeline: FinancialMappingPipeline) -> None:
    print_section("DEMO 1 — Dict Input (Synonym + Fuzzy)")

    raw_data = {
        "Profit After Tax": 500_000,
        "Owner Funds": 1_200_000,
        "Current Assets": 3_450_000,
        "Total Current Liabilities": 2_100_000,
        "Long Term Borrowings": 800_000,
        "Share Capital": 1_000_000,
        "Reserves and Surplus": 2_500_000,
        "Gross Profit": 1_800_000,
        "Indirect Expenses": 350_000,
        "Cash Sales": 900_000,
        "Credit Sales": 1_600_000,
        "Other Operating Income": 120_000,
        "Operating Expenses": 1_200_000,
        "Cash Accruals": 450_000,
        "Loan Installment": 200_000,
        "Interest Expense": 150_000,
        "Opening Stock": 600_000,
        "Closing Stock": 750_000,
        "Net Purchases": 1_400_000,
        "Direct Costs": 800_000,
        "Opening Trade Receivables": 500_000,
        "Closing Trade Receivables": 650_000,
        "Net Sales": 4_200_000,
        "Non-Current Liabilities": 950_000,
        "Intangible Assets": 300_000,
        "Fixed Costs": 400_000,
        "Selling Price": 250,
        "Variable Costs": 180,
        # These test fuzzy matching (not exact synonyms)
        "Depn & Amortisation": 220_000,
        "Income Tax Provision": 180_000,
        "Total Turnover": 4_500_000,
    }

    result = pipeline.map_dict(raw_data)
    print_output(result)


# ======================================================================
# Demo 2 — CSV input
# ======================================================================

def demo_csv(pipeline: FinancialMappingPipeline) -> None:
    print_section("DEMO 2 — CSV Input")

    csv_path = Path(__file__).resolve().parent.parent / "data" / "sample_balance_sheet.csv"
    if not csv_path.exists():
        print(f"  [SKIP] CSV sample not found at {csv_path}")
        return

    result = pipeline.map_csv(csv_path)
    print_output(result)


# ======================================================================
# Demo 3 — JSON input
# ======================================================================

def demo_json(pipeline: FinancialMappingPipeline) -> None:
    print_section("DEMO 3 — JSON Input")

    json_path = Path(__file__).resolve().parent.parent / "data" / "sample_balance_sheet.json"
    if not json_path.exists():
        print(f"  [SKIP] JSON sample not found at {json_path}")
        return

    result = pipeline.map_json(json_path)
    print_output(result)


# ======================================================================
# Demo 4 — Mapped dict for downstream calculations
# ======================================================================

def demo_ratio_ready(pipeline: FinancialMappingPipeline) -> None:
    print_section("DEMO 4 — Ratio-Ready Mapped Dict")

    raw_data = {
        "Current Assets": 3_450_000,
        "Current Liabilities": 2_100_000,
        "Net Profit": 500_000,
        "Net Sales": 4_200_000,
        "Total Assets": 8_000_000,
        "Total Debt": 1_600_000,
        "Equity": 4_000_000,
    }

    result = pipeline.map_dict(raw_data)
    mapped = result.mapped_dict()

    print("\n  Standardised values ready for ratio engine:")
    for k, v in mapped.items():
        print(f"    {k:30s} = {v:>15,.2f}")

    # Example ratio calculation
    ca = mapped.get("Current Assets", 0)
    cl = mapped.get("Current Liabilities", 0)
    if cl:
        print(f"\n  Current Ratio = {ca / cl:.2f}")

    np_ = mapped.get("Net Profit", 0)
    ns = mapped.get("Net Sales", 0)
    if ns:
        print(f"  Net Profit Margin = {np_ / ns * 100:.2f}%")


# ======================================================================
# Main
# ======================================================================

def main() -> None:
    # Configure pipeline with moderate thresholds
    config = PipelineConfig(
        matching=MatchingConfig(
            fuzzy_threshold=75.0,
            fuzzy_ambiguity_delta=5.0,
            strict_mode=False,
        ),
        validation=ValidationConfig(
            required_fields=[],
            error_on_duplicate=False,
        ),
        log_level=logging.WARNING,  # Quieter for demo output
    )

    pipeline = FinancialMappingPipeline(config)

    demo_dict(pipeline)
    demo_csv(pipeline)
    demo_json(pipeline)
    demo_ratio_ready(pipeline)

    print("\n" + "=" * 72)
    print("  All demos complete.")
    print("=" * 72)


if __name__ == "__main__":
    main()
