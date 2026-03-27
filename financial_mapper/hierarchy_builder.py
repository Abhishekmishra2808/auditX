"""
Hierarchy Builder for Balance Sheet Data.

Converts flat extracted rows into a hierarchical tree structure that
reflects the natural parent–child–total relationships found in balance
sheets and income statements.

Usage
-----
>>> from financial_mapper.hierarchy_builder import build_hierarchy
>>> rows = [
...     {"label": "Current Assets", "value": None},
...     {"label": "Cash and Cash Equivalents", "value": 100000},
...     {"label": "Trade Receivables", "value": 50000},
...     {"label": "Total Current Assets", "value": 150000},
... ]
>>> tree = build_hierarchy(rows)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from financial_mapper.logging_setup import get_logger

logger = get_logger("hierarchy_builder")

# ---------------------------------------------------------------------------
# Default section-detection keywords (config-overridable)
# ---------------------------------------------------------------------------

DEFAULT_SECTION_KEYWORDS: List[str] = [
    "assets",
    "liabilities",
    "equity",
    "income",
    "expenses",
    "revenue",
    "provisions",
    "borrowings",
    "investments",
    "reserves",
    "capital",
    "shareholders funds",
    "stockholders equity",
    "non-current assets",
    "current assets",
    "non-current liabilities",
    "current liabilities",
    "fixed assets",
    "other assets",
    "other liabilities",
    "sources of funds",
    "application of funds",
]

DEFAULT_TOTAL_PREFIX: str = "Total"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_hierarchy(
    rows: List[Dict[str, Any]],
    *,
    section_keywords: Optional[Sequence[str]] = None,
    total_prefix: str = DEFAULT_TOTAL_PREFIX,
) -> Dict[str, Any]:
    """Convert a flat list of balance-sheet rows into a hierarchical tree.

    Parameters
    ----------
    rows:
        Each dict must have ``"label"`` (str) and ``"value"`` (float | None).
        A ``None`` value hints at a section header; a non-None value hints
        at a leaf (line-item) or explicit total.
    section_keywords:
        Lowercased keywords that identify section headers.  Falls back to
        ``DEFAULT_SECTION_KEYWORDS`` when not supplied.
    total_prefix:
        Prefix used to detect total rows (e.g. ``"Total Current Assets"``).

    Returns
    -------
    dict
        Nested structure::

            {
              "Current Assets": {
                "children": {"Cash and Cash Equivalents": 100000, ...},
                "total": 150000
              },
              ...
            }
    """
    keywords = {k.lower() for k in (section_keywords or DEFAULT_SECTION_KEYWORDS)}
    total_prefix_lower = total_prefix.lower().strip()

    # Phase 1: classify each row
    classified = _classify_rows(rows, keywords, total_prefix_lower)

    # Phase 2: build the tree from classified rows
    tree = _assemble_tree(classified, total_prefix_lower)

    logger.info(
        "Hierarchy built: %d top-level sections, %d total rows processed",
        len(tree),
        len(rows),
    )
    return tree


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ROW_TYPE_SECTION = "section"
_ROW_TYPE_TOTAL = "total"
_ROW_TYPE_ITEM = "item"


def _classify_rows(
    rows: List[Dict[str, Any]],
    keywords: set[str],
    total_prefix_lower: str,
) -> List[Dict[str, Any]]:
    """Tag each row as section / total / item."""
    classified: List[Dict[str, Any]] = []

    for row in rows:
        label = str(row.get("label", "")).strip()
        value = row.get("value")

        if not label:
            continue

        label_lower = label.lower().strip()

        # Detect "Total X" rows
        if label_lower.startswith(total_prefix_lower + " "):
            classified.append({
                "label": label,
                "value": value,
                "type": _ROW_TYPE_TOTAL,
                "parent_hint": label[len(total_prefix_lower):].strip(),
            })
            continue

        # Detect section headers: value is None and label matches a keyword
        is_section = False
        if value is None:
            is_section = True
        elif _is_section_keyword(label_lower, keywords):
            # Some sheets have section headers with a value of 0 or None-like
            if value == 0 or value == "" or value is None:
                is_section = True

        if is_section and _is_section_keyword(label_lower, keywords):
            classified.append({
                "label": label,
                "value": value,
                "type": _ROW_TYPE_SECTION,
            })
            continue

        # Also treat value-less rows that are not keywords as implicit sections
        if value is None:
            classified.append({
                "label": label,
                "value": None,
                "type": _ROW_TYPE_SECTION,
            })
            continue

        # Default: leaf item
        classified.append({
            "label": label,
            "value": value,
            "type": _ROW_TYPE_ITEM,
        })

    return classified


def _is_section_keyword(label_lower: str, keywords: set[str]) -> bool:
    """Check if a label matches any section keyword (exact or substring)."""
    if label_lower in keywords:
        return True
    for kw in keywords:
        if kw in label_lower:
            return True
    return False


def _assemble_tree(
    classified: List[Dict[str, Any]],
    total_prefix_lower: str,
) -> Dict[str, Any]:
    """Walk through classified rows and build the nested tree.

    Strategy: maintain a stack of open sections.  Items are added as
    children of the most-recently-opened section.  A "Total X" row
    closes the section whose name matches *X*.
    """
    tree: Dict[str, Any] = {}
    section_stack: List[Dict[str, Any]] = []  # stack of open section nodes

    for row in classified:
        rtype = row["type"]
        label = row["label"]
        value = row["value"]

        if rtype == _ROW_TYPE_SECTION:
            # Open a new section
            node: Dict[str, Any] = {
                "children": {},
                "total": None,
                "_label": label,
            }
            if section_stack:
                # Nest inside current section
                section_stack[-1]["children"][label] = node
            else:
                tree[label] = node
            section_stack.append(node)
            logger.debug("Opened section: %r (depth=%d)", label, len(section_stack))

        elif rtype == _ROW_TYPE_TOTAL:
            parent_hint = row.get("parent_hint", "")
            total_value = value

            # Find the matching section to close
            matched = _pop_matching_section(section_stack, parent_hint)
            if matched is not None:
                matched["total"] = total_value
                logger.debug(
                    "Closed section %r with total=%s",
                    matched.get("_label"),
                    total_value,
                )
            else:
                # No matching open section — store as a standalone item
                if section_stack:
                    section_stack[-1]["children"][label] = total_value
                else:
                    tree[label] = {"children": {}, "total": total_value}
                logger.debug(
                    "Total row %r has no matching open section; stored standalone",
                    label,
                )

        elif rtype == _ROW_TYPE_ITEM:
            if section_stack:
                section_stack[-1]["children"][label] = value
            else:
                # No open section — store at top level as a standalone value
                tree[label] = value
            logger.debug("Item %r = %s → parent=%s", label, value,
                         section_stack[-1].get("_label") if section_stack else "ROOT")

    # Close any remaining open sections (no explicit "Total" row)
    for node in section_stack:
        logger.debug(
            "Section %r was never closed by a Total row",
            node.get("_label"),
        )

    # Clean up internal labels
    _strip_internal_keys(tree)

    return tree


def _pop_matching_section(
    stack: List[Dict[str, Any]],
    parent_hint: str,
) -> Optional[Dict[str, Any]]:
    """Pop the section from the stack whose label best matches *parent_hint*.

    Searches from top of stack (most recent) to bottom.
    """
    hint_lower = parent_hint.lower().strip()

    for i in range(len(stack) - 1, -1, -1):
        section_label = stack[i].get("_label", "").lower().strip()
        if section_label == hint_lower or hint_lower in section_label or section_label in hint_lower:
            return stack.pop(i)

    # If no match found, pop the top-most section as fallback
    if stack:
        return stack.pop()

    return None


def _strip_internal_keys(tree: Dict[str, Any]) -> None:
    """Remove ``_label`` keys that were used during assembly."""
    for key, val in tree.items():
        if isinstance(val, dict):
            val.pop("_label", None)
            children = val.get("children", {})
            if isinstance(children, dict):
                _strip_internal_keys(children)


# ---------------------------------------------------------------------------
# Utility: flatten tree back to canonical dict
# ---------------------------------------------------------------------------


def flatten_hierarchy(tree: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a hierarchy tree into a simple ``{label: value}`` dict.

    Collects all leaf values and section totals.  Useful for passing
    the result into the canonical mapping stage.

    Returns
    -------
    dict
        ``{label: numeric_value}`` for every label that has a value.
    """
    result: Dict[str, Any] = {}

    for label, node in tree.items():
        if isinstance(node, dict):
            # Section node
            children = node.get("children", {})
            total = node.get("total")

            # Add the section total if present
            if total is not None:
                result[label] = total

            # Recurse into children
            for child_label, child_val in children.items():
                if isinstance(child_val, dict):
                    # Nested section
                    nested = flatten_hierarchy({child_label: child_val})
                    result.update(nested)
                elif child_val is not None:
                    result[child_label] = child_val
        elif node is not None:
            # Standalone value at root level
            result[label] = node

    return result
