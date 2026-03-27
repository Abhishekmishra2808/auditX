"""Canonical financial synonyms used by the hybrid mapper."""

from __future__ import annotations

from typing import Dict, Iterable, List

from financial_mapper.normalizer import normalize

# Core canonical fields used by mapping + ratio engine.
SYNONYMS: Dict[str, List[str]] = {
    "cash": [
        "cash",
        "cash balance",
        "cash and cash equivalents",
        "cash in hand",
        "bank balance",
        "bank balances",
        "bank deposits",
        "liquid funds",
    ],
    "receivables": [
        "receivables",
        "accounts receivable",
        "trade receivables",
        "sundry debtors",
        "debtors",
        "bills receivable",
    ],
    "accounts_payable": [
        "accounts payable",
        "trade payables",
        "sundry creditors",
        "creditors",
        "bills payable",
    ],
    "inventory": [
        "inventory",
        "inventories",
        "stock",
        "stock in trade",
        "closing stock",
        "goods inventory",
    ],
    "current_assets": [
        "current assets",
        "total current assets",
        "ca",
    ],
    "current_liabilities": [
        "current liabilities",
        "total current liabilities",
        "short term liabilities",
        "cl",
    ],
    "total_assets": [
        "total assets",
        "assets total",
        "total asset",
    ],
    "total_liabilities": [
        "total liabilities",
        "liabilities total",
        "total liability",
    ],
    "debt": [
        "debt",
        "total debt",
        "total borrowings",
        "borrowings",
        "loans",
        "long term borrowings",
        "long-term borrowings",
    ],
    "equity": [
        "equity",
        "owners funds",
        "owner funds",
        "net worth",
        "shareholders funds",
        "share capital",
        "reserves and surplus",
        "reserves & surplus",
    ],
}

DEFAULT_ALLOWED_FIELDS: tuple[str, ...] = tuple(SYNONYMS.keys())


def build_lookup(extra_synonyms: Dict[str, Iterable[str]] | None = None) -> Dict[str, str]:
    """Build normalized term -> canonical lookup from synonym definitions."""
    lookup: Dict[str, str] = {}

    def _add_group(canonical: str, terms: Iterable[str]) -> None:
        lookup[normalize(canonical)] = canonical
        for term in terms:
            lookup[normalize(term)] = canonical

    for canonical, terms in SYNONYMS.items():
        _add_group(canonical, terms)

    if extra_synonyms:
        for canonical, terms in extra_synonyms.items():
            _add_group(canonical, terms)

    return lookup
