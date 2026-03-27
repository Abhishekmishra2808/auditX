"""
Financial Mapper — Semantic Balance Sheet Extraction Engine.

A production-grade module that reads balance sheet data with inconsistent
column names and maps all values to a standardized financial schema
used for ratio calculations.

All mappings are confidence-scored and auditable. The system never guesses
silently — ambiguous or low-confidence mappings are flagged explicitly.
"""

__version__ = "1.1.0"
__author__ = "Financial Mapper Team"

from financial_mapper.aggregator import compute_aggregates  # noqa: F401
from financial_mapper.hierarchy_builder import build_hierarchy  # noqa: F401
from financial_mapper.pipeline import FinancialMappingPipeline  # noqa: F401
