"""
Synonym Dictionary Engine.

A curated, configurable mapping from commonly-seen financial label variants
to their canonical names.  The dictionary is the **first** (and most
trustworthy) matching layer — it fires before fuzzy matching.

Design decisions
----------------
* Keys are stored **normalised** (lowercase, stripped) so that a single
  normalisation pass on the input label is sufficient for lookup.
* The built-in dictionary ships with ~200 entries covering Indian and
  international financial reporting conventions.
* Users can extend at runtime via ``load_custom_synonyms`` (JSON file) or
  ``add_synonym`` / ``add_synonyms``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from financial_mapper.logging_setup import get_logger
from financial_mapper.normalizer import LabelNormalizer
from financial_mapper.schema import CANONICAL_NAMES, canonical_lookup

logger = get_logger("synonym_mapper")


# ---------------------------------------------------------------------------
# Built-in synonym dictionary
# ---------------------------------------------------------------------------
# Convention: key = normalised variant, value = canonical name exactly as
# defined in ``CanonicalField.value``.

_BUILTIN_SYNONYMS: Dict[str, str] = {
    # --- Current Assets ---
    "current assets": "Current Assets",
    "total current assets": "Current Assets",
    "current assets total": "Current Assets",
    "ca": "Current Assets",
    "net current assets": "Current Assets",

    # --- Current Liabilities ---
    "current liabilities": "Current Liabilities",
    "total current liabilities": "Current Liabilities",
    "current liabilities total": "Current Liabilities",
    "cl": "Current Liabilities",
    "current liabilities & provisions": "Current Liabilities",
    "current liabilities and provisions": "Current Liabilities",

    # --- Long-term Borrowings ---
    "long-term borrowings": "Long-term Borrowings",
    "long term borrowings": "Long-term Borrowings",
    "lt borrowings": "Long-term Borrowings",
    "long term loans": "Long-term Borrowings",
    "long-term loans": "Long-term Borrowings",
    "term loans": "Long-term Borrowings",
    "secured loans": "Long-term Borrowings",
    "unsecured loans": "Long-term Borrowings",
    "borrowings non-current": "Long-term Borrowings",
    "non-current borrowings": "Long-term Borrowings",

    # --- Long-term Provisions ---
    "long-term provisions": "Long-term Provisions",
    "long term provisions": "Long-term Provisions",
    "lt provisions": "Long-term Provisions",
    "non-current provisions": "Long-term Provisions",
    "provisions non-current": "Long-term Provisions",

    # --- Share Capital ---
    "share capital": "Share Capital",
    "equity share capital": "Share Capital",
    "paid-up capital": "Share Capital",
    "paid up capital": "Share Capital",
    "issued capital": "Share Capital",
    "authorized capital": "Share Capital",
    "authorised capital": "Share Capital",
    "share capital & premium": "Share Capital",

    # --- Reserves & Surplus ---
    "reserves & surplus": "Reserves & Surplus",
    "reserves and surplus": "Reserves & Surplus",
    "reserves": "Reserves & Surplus",
    "surplus": "Reserves & Surplus",
    "retained earnings": "Reserves & Surplus",
    "other reserves": "Reserves & Surplus",
    "general reserve": "Reserves & Surplus",
    "profit & loss account": "Reserves & Surplus",
    "profit and loss account": "Reserves & Surplus",
    "accumulated profits": "Reserves & Surplus",

    # --- Gross Profit ---
    "gross profit": "Gross Profit",
    "gp": "Gross Profit",
    "gross margin": "Gross Profit",
    "gross income": "Gross Profit",

    # --- Indirect Expenses ---
    "indirect expenses": "Indirect Expenses",
    "indirect costs": "Indirect Expenses",
    "overhead expenses": "Indirect Expenses",
    "overheads": "Indirect Expenses",
    "administrative expenses": "Indirect Expenses",
    "admin expenses": "Indirect Expenses",

    # --- Cash Sales ---
    "cash sales": "Cash Sales",
    "cash revenue": "Cash Sales",

    # --- Credit Sales ---
    "credit sales": "Credit Sales",
    "credit revenue": "Credit Sales",
    "sales on credit": "Credit Sales",

    # --- Other Operating Income ---
    "other operating income": "Other Operating Income",
    "other income": "Other Operating Income",
    "non-operating income": "Other Operating Income",
    "miscellaneous income": "Other Operating Income",

    # --- Operating Expenses ---
    "operating expenses": "Operating Expenses",
    "opex": "Operating Expenses",
    "operational expenses": "Operating Expenses",

    # --- Cash Accruals ---
    "cash accruals": "Cash Accruals",
    "cash accrual": "Cash Accruals",
    "net cash accruals": "Cash Accruals",

    # --- Loan Installment ---
    "loan installment": "Loan Installment",
    "loan instalment": "Loan Installment",
    "emi": "Loan Installment",
    "loan repayment": "Loan Installment",
    "debt repayment": "Loan Installment",

    # --- Interest ---
    "interest": "Interest",
    "interest expense": "Interest",
    "interest cost": "Interest",
    "finance cost": "Interest",
    "finance costs": "Interest",
    "interest paid": "Interest",
    "interest on borrowings": "Interest",

    # --- Inventory items ---
    "opening inventory": "Opening Inventory",
    "opening stock": "Opening Inventory",
    "beginning inventory": "Opening Inventory",
    "inventory at beginning": "Opening Inventory",
    "closing inventory": "Closing Inventory",
    "closing stock": "Closing Inventory",
    "ending inventory": "Closing Inventory",
    "inventory at end": "Closing Inventory",

    # --- Net Purchases ---
    "net purchases": "Net Purchases",
    "purchases": "Net Purchases",
    "total purchases": "Net Purchases",

    # --- Direct Expenses ---
    "direct expenses": "Direct Expenses",
    "direct costs": "Direct Expenses",
    "manufacturing expenses": "Direct Expenses",
    "production expenses": "Direct Expenses",
    "factory expenses": "Direct Expenses",

    # --- Debtors ---
    "opening debtors": "Opening Debtors",
    "opening trade receivables": "Opening Debtors",
    "debtors at beginning": "Opening Debtors",
    "closing debtors": "Closing Debtors",
    "closing trade receivables": "Closing Debtors",
    "debtors at end": "Closing Debtors",

    # --- Net Sales ---
    "net sales": "Net Sales",
    "total sales": "Net Sales",
    "sales": "Net Sales",
    "turnover": "Net Sales",
    "net turnover": "Net Sales",
    "total turnover": "Net Sales",
    "revenue from operations": "Net Sales",

    # --- Long-term Liabilities ---
    "long-term liabilities": "Long-term Liabilities",
    "long term liabilities": "Long-term Liabilities",
    "non-current liabilities": "Long-term Liabilities",
    "total non-current liabilities": "Long-term Liabilities",

    # --- Intangible Assets ---
    "intangible assets": "Intangible Assets",
    "goodwill": "Intangible Assets",
    "patents": "Intangible Assets",
    "trademarks": "Intangible Assets",
    "intangibles": "Intangible Assets",

    # --- Cost items ---
    "fixed cost": "Fixed Cost",
    "fixed costs": "Fixed Cost",
    "fixed expenses": "Fixed Cost",
    "selling price": "Selling Price",
    "sale price": "Selling Price",
    "sp": "Selling Price",
    "variable cost": "Variable Cost",
    "variable costs": "Variable Cost",
    "variable expenses": "Variable Cost",

    # --- Extended / derived fields ---
    "net profit": "Net Profit",
    "profit after tax": "Net Profit",
    "pat": "Net Profit",
    "net income": "Net Profit",
    "bottom line": "Net Profit",
    "profit for the year": "Net Profit",
    "profit for the period": "Net Profit",

    "net worth": "Net Worth",
    "networth": "Net Worth",
    "owner funds": "Net Worth",
    "owners funds": "Net Worth",
    "shareholders funds": "Net Worth",
    "shareholders equity": "Net Worth",
    "stockholders equity": "Net Worth",
    "total equity": "Net Worth",

    "total assets": "Total Assets",
    "total asset": "Total Assets",

    "total liabilities": "Total Liabilities",
    "total liability": "Total Liabilities",

    "ebitda": "EBITDA",
    "operating profit before depreciation": "EBITDA",
    "earnings before interest tax depreciation & amortization": "EBITDA",

    "depreciation": "Depreciation",
    "depreciation & amortization": "Depreciation",
    "depreciation and amortisation": "Depreciation",
    "dep": "Depreciation",

    "tax": "Tax",
    "income tax": "Tax",
    "provision for tax": "Tax",
    "tax expense": "Tax",
    "taxation": "Tax",

    "revenue": "Revenue",
    "total revenue": "Revenue",
    "gross revenue": "Revenue",
    "income from operations": "Revenue",

    "total debt": "Total Debt",
    "total borrowings": "Total Debt",
    "debt": "Total Debt",

    "equity": "Equity",
    "owner equity": "Equity",
    "equity capital": "Equity",

    "working capital": "Working Capital",
    "net working capital": "Working Capital",

    "tangible assets": "Tangible Assets",
    "net tangible assets": "Tangible Assets",
    "property plant & equipment": "Tangible Assets",
    "property plant and equipment": "Tangible Assets",
    "ppe": "Tangible Assets",

    "fixed assets": "Fixed Assets",
    "non-current assets": "Fixed Assets",
    "total fixed assets": "Fixed Assets",
    "net fixed assets": "Fixed Assets",
    "net block": "Fixed Assets",
    "gross block": "Fixed Assets",

    "inventory": "Inventory",
    "inventories": "Inventory",
    "stock": "Inventory",
    "stocks": "Inventory",

    "trade receivables": "Trade Receivables",
    "sundry debtors": "Trade Receivables",
    "accounts receivable": "Trade Receivables",
    "debtors": "Trade Receivables",

    "trade payables": "Trade Payables",
    "sundry creditors": "Trade Payables",
    "accounts payable": "Trade Payables",
    "creditors": "Trade Payables",

    "cash and cash equivalents": "Cash and Cash Equivalents",
    "cash & cash equivalents": "Cash and Cash Equivalents",
    "cash and bank balances": "Cash and Cash Equivalents",
    "cash & bank balances": "Cash and Cash Equivalents",
    "cash": "Cash and Cash Equivalents",
    "bank balance": "Cash and Cash Equivalents",

    "total income": "Total Income",
    "total expenses": "Total Expenses",
    "total expenditure": "Total Expenses",
    "net revenue": "Net Revenue",

    "cost of goods sold": "Cost of Goods Sold",
    "cogs": "Cost of Goods Sold",
    "cost of sales": "Cost of Goods Sold",
    "cost of revenue": "Cost of Goods Sold",

    "operating profit": "Operating Profit",
    "ebit": "Operating Profit",
    "earnings before interest and tax": "Operating Profit",
    "operating income": "Operating Profit",

    "profit before tax": "Profit Before Tax",
    "pbt": "Profit Before Tax",
    "earnings before tax": "Profit Before Tax",
    "income before tax": "Profit Before Tax",
}


class SynonymMapper:
    """Dictionary-based label → canonical-name mapper.

    The mapper holds a normalised synonym dictionary.  Look-ups are O(1)
    hash-table hits; no fuzzy logic or ML is involved.

    Parameters
    ----------
    normalizer:
        An instance of ``LabelNormalizer`` used to normalise both incoming
        labels and any user-supplied synonyms.
    extra_synonyms:
        Optional dict of additional synonyms to merge in at construction time.
    """

    def __init__(
        self,
        normalizer: LabelNormalizer,
        extra_synonyms: Optional[Dict[str, str]] = None,
    ) -> None:
        self._normalizer = normalizer
        # Build the internal dictionary (keys already normalised in the
        # built-in dict; we normalise again to be safe).
        self._dict: Dict[str, str] = {}
        for variant, canonical in _BUILTIN_SYNONYMS.items():
            nk = self._normalizer.normalize_label(variant)
            self._dict[nk] = canonical

        if extra_synonyms:
            self.add_synonyms(extra_synonyms)

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def lookup(self, normalised_label: str) -> Optional[str]:
        """Return canonical name if the normalised label is in the dictionary.

        Parameters
        ----------
        normalised_label:
            A label that has **already** been through ``LabelNormalizer``.

        Returns
        -------
        str | None
            Canonical name, or ``None`` if not found.
        """
        result = self._dict.get(normalised_label)
        if result:
            logger.info(
                "Synonym hit: %r → %r (confidence=100)", normalised_label, result
            )
        return result

    # ------------------------------------------------------------------ #
    # Extension API
    # ------------------------------------------------------------------ #

    def add_synonym(self, variant: str, canonical: str) -> None:
        """Register a single new synonym.

        Raises
        ------
        ValueError
            If ``canonical`` is not a recognised canonical name.
        """
        if canonical not in CANONICAL_NAMES:
            cf = canonical_lookup(canonical)
            if cf is None:
                raise ValueError(
                    f"Unknown canonical name {canonical!r}. "
                    f"Must be one of the CanonicalField values."
                )
            canonical = cf.value

        nk = self._normalizer.normalize_label(variant)
        if nk in self._dict and self._dict[nk] != canonical:
            logger.warning(
                "Overwriting synonym %r: %r → %r",
                nk,
                self._dict[nk],
                canonical,
            )
        self._dict[nk] = canonical
        logger.debug("Added synonym: %r → %r", nk, canonical)

    def add_synonyms(self, mapping: Dict[str, str]) -> None:
        """Bulk-add synonyms from a ``{variant: canonical}`` dict."""
        for variant, canonical in mapping.items():
            self.add_synonym(variant, canonical)

    def load_custom_synonyms(self, path: Path) -> int:
        """Load synonyms from a JSON file (``{variant: canonical}``).

        Returns the number of entries added.
        """
        with open(path, encoding="utf-8") as fh:
            data: Dict[str, str] = json.load(fh)
        self.add_synonyms(data)
        logger.info("Loaded %d custom synonyms from %s", len(data), path)
        return len(data)

    def save_new_mapping(self, raw_label: str, canonical: str, output_path: Path) -> None:
        """Persist a user-confirmed mapping to a JSON file for future use.

        This is called when a user confirms an LLM-suggested mapping or manually
        corrects an unmapped label. The mapping is added to the in-memory dictionary
        and also written to a JSON file for persistence across runs.

        Parameters
        ----------
        raw_label : str
            The raw input label (e.g., "Current Liab.")
        canonical : str
            The canonical field name it should map to
        output_path : Path
            File path where the mapping will be appended/saved
        """
        # First validate and add to in-memory dictionary
        self.add_synonym(raw_label, canonical)

        # Then persist to disk
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing custom synonyms if file exists
            if output_path.exists():
                with open(output_path, encoding="utf-8") as fh:
                    data: Dict[str, str] = json.load(fh)
            else:
                data = {}

            # Add/update the new mapping
            data[raw_label] = canonical

            # Write back to file
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)

            logger.info(
                "Persisted new mapping: %r → %r to %s",
                raw_label,
                canonical,
                output_path,
            )
        except Exception as e:
            logger.error("Failed to persist mapping to %s: %s", output_path, e)


    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    @property
    def size(self) -> int:
        return len(self._dict)

    def all_synonyms(self) -> Dict[str, str]:
        """Return a *copy* of the internal dictionary."""
        return dict(self._dict)
