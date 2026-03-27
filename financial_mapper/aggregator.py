"""
Aggregation Layer for Canonical Financial Data.

Computes derived / missing canonical fields from the hierarchy tree and
mapped values.  If an expected aggregate (e.g. "Current Assets") is missing
but its constituent children are present, this layer can fill the gap.

Usage
-----
>>> from financial_mapper.aggregator import compute_aggregates
>>> mapped = {"Cash and Cash Equivalents": 100000, "Trade Receivables": 50000}
>>> tree = {"Current Assets": {"children": {...}, "total": 150000}}
>>> enriched = compute_aggregates(tree, mapped)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from financial_mapper.logging_setup import get_logger

logger = get_logger("aggregator")

# ---------------------------------------------------------------------------
# Derivation rules — config-driven, not hardcoded
# ---------------------------------------------------------------------------

# Each rule: (target_canonical, [list_of_source_canonicals], operation)
# operation is "sum" or "subtract"

DERIVATION_RULES: List[Dict[str, Any]] = [
    {
        "target": "Working Capital",
        "sources": ["Current Assets", "Current Liabilities"],
        "operation": "subtract",  # CA - CL
        "description": "Current Assets − Current Liabilities",
    },
    {
        "target": "Total Debt",
        "sources": ["Long-term Borrowings", "Current Liabilities"],
        "operation": "sum",
        "description": "Long-term Borrowings + Current Liabilities",
    },
    {
        "target": "Net Worth",
        "sources": ["Share Capital", "Reserves & Surplus"],
        "operation": "sum",
        "description": "Share Capital + Reserves & Surplus",
    },
    {
        "target": "Gross Profit",
        "sources": ["Revenue", "Cost of Goods Sold"],
        "operation": "subtract",
        "description": "Revenue − Cost of Goods Sold",
    },
    {
        "target": "Operating Profit",
        "sources": ["Gross Profit", "Operating Expenses"],
        "operation": "subtract",
        "description": "Gross Profit − Operating Expenses",
    },
    {
        "target": "EBITDA",
        "sources": ["Operating Profit", "Depreciation"],
        "operation": "sum",
        "description": "Operating Profit + Depreciation",
    },
    {
        "target": "Profit Before Tax",
        "sources": ["Operating Profit", "Interest"],
        "operation": "subtract",
        "description": "Operating Profit − Interest",
    },
    {
        "target": "Net Profit",
        "sources": ["Profit Before Tax", "Tax"],
        "operation": "subtract",
        "description": "Profit Before Tax − Tax",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_aggregates(
    tree: Dict[str, Any],
    mapped_values: Dict[str, Any],
    *,
    tolerance: float = 0.01,
    extra_rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Enrich *mapped_values* with computed aggregates from the hierarchy.

    Parameters
    ----------
    tree:
        The hierarchy tree as produced by ``build_hierarchy()``.
    mapped_values:
        ``{canonical_name: value}`` from the canonical mapping stage.
    tolerance:
        Relative tolerance for children-vs-total cross-checks.
        ``abs(computed - stated) / stated <= tolerance`` is acceptable.
    extra_rules:
        Additional derivation rules to append to the built-in set.

    Returns
    -------
    dict
        A copy of *mapped_values* enriched with any computable missing fields.
        Also includes any warnings about mismatches.
    """
    enriched = dict(mapped_values)
    warnings: List[str] = []

    # Phase 1: fill missing section totals from hierarchy children
    _fill_from_hierarchy(tree, enriched, warnings, tolerance)

    # Phase 2: apply derivation rules for still-missing fields
    rules = list(DERIVATION_RULES)
    if extra_rules:
        rules.extend(extra_rules)

    _apply_derivation_rules(enriched, rules, warnings)

    if warnings:
        logger.info(
            "Aggregation completed with %d warning(s):\n  %s",
            len(warnings),
            "\n  ".join(warnings),
        )
    else:
        logger.info("Aggregation completed — no warnings")

    # Attach warnings as metadata
    enriched["_aggregation_warnings"] = warnings
    return enriched


# ---------------------------------------------------------------------------
# Hierarchy-based aggregation
# ---------------------------------------------------------------------------


def _fill_from_hierarchy(
    tree: Dict[str, Any],
    values: Dict[str, Any],
    warnings: List[str],
    tolerance: float,
) -> None:
    """For each section in the tree, compute children sum if total is missing."""
    for section_label, node in tree.items():
        if not isinstance(node, dict):
            continue

        children = node.get("children", {})
        stated_total = node.get("total")

        # Recursively handle nested sections first
        for child_label, child_val in children.items():
            if isinstance(child_val, dict):
                _fill_from_hierarchy(
                    {child_label: child_val}, values, warnings, tolerance
                )

        # Compute the sum of direct children values
        children_sum = _sum_children(children, values)

        if children_sum is not None:
            # Cross-check against stated total
            if stated_total is not None:
                _cross_check(section_label, children_sum, stated_total, warnings, tolerance)

            # Fill in the section value if missing from mapped_values
            if section_label not in values or values[section_label] is None:
                source = stated_total if stated_total is not None else children_sum
                values[section_label] = source
                logger.info(
                    "Aggregated %r = %s (source: %s)",
                    section_label,
                    source,
                    "stated total" if stated_total is not None else "children sum",
                )
        elif stated_total is not None and (
            section_label not in values or values[section_label] is None
        ):
            values[section_label] = stated_total
            logger.info(
                "Filled %r = %s from stated total (no summable children)",
                section_label,
                stated_total,
            )


def _sum_children(
    children: Dict[str, Any],
    values: Dict[str, Any],
) -> Optional[float]:
    """Sum numeric children values.  Returns None if no numeric children."""
    total = 0.0
    has_numeric = False

    for child_label, child_val in children.items():
        if isinstance(child_val, dict):
            # Nested section — use its total or computed total from values
            nested_val = child_val.get("total")
            if nested_val is None:
                nested_val = values.get(child_label)
            if nested_val is not None and isinstance(nested_val, (int, float)):
                total += float(nested_val)
                has_numeric = True
        elif child_val is not None and isinstance(child_val, (int, float)):
            total += float(child_val)
            has_numeric = True

    return total if has_numeric else None


def _cross_check(
    label: str,
    computed: float,
    stated: float,
    warnings: List[str],
    tolerance: float,
) -> None:
    """Compare computed children sum against stated total."""
    if stated == 0:
        if computed != 0:
            warnings.append(
                f"[{label}] Stated total is 0 but children sum to {computed:.2f}"
            )
        return

    relative_diff = abs(computed - stated) / abs(stated)
    if relative_diff > tolerance:
        warnings.append(
            f"[{label}] Children sum ({computed:.2f}) ≠ stated total "
            f"({stated:.2f}), relative diff = {relative_diff:.4f} "
            f"(tolerance={tolerance})"
        )
        logger.warning(
            "Hierarchy mismatch for %r: computed=%s, stated=%s, diff=%.4f",
            label,
            computed,
            stated,
            relative_diff,
        )


# ---------------------------------------------------------------------------
# Derivation-rule engine
# ---------------------------------------------------------------------------


def _apply_derivation_rules(
    values: Dict[str, Any],
    rules: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    """Apply derivation rules to fill in any remaining missing fields.

    Rules are applied in order.  Each rule is attempted at most once per call.
    A rule only fires if the target is **missing** and all sources are present.
    """
    for rule in rules:
        target = rule["target"]
        sources = rule["sources"]
        operation = rule["operation"]

        # Skip if target already has a value
        if target in values and values[target] is not None:
            continue

        # Check all sources are available
        source_values = []
        all_present = True
        for src in sources:
            val = values.get(src)
            if val is None or not isinstance(val, (int, float)):
                all_present = False
                break
            source_values.append(float(val))

        if not all_present:
            continue

        # Compute
        if operation == "sum":
            result = sum(source_values)
        elif operation == "subtract":
            result = source_values[0] - sum(source_values[1:])
        else:
            logger.warning("Unknown derivation operation: %s", operation)
            continue

        values[target] = result
        logger.info(
            "Derived %r = %s via %s",
            target,
            result,
            rule.get("description", operation),
        )
