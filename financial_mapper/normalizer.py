"""
Label Normalization Layer.

Transforms raw financial labels into a uniform representation so that
downstream matchers operate on clean, comparable strings.

Transformations applied (in order):
1. Strip leading / trailing whitespace
2. Lowercase conversion
3. Remove parenthetical negative-number markers → prepend '-'
4. Strip punctuation (except hyphens inside words)
5. Collapse multiple spaces / underscores into a single space
6. Numeric clean-up (commas in numbers, currency symbols)
"""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from financial_mapper.logging_setup import get_logger

logger = get_logger("normalizer")


class LabelNormalizer:
    """Stateless label normaliser.  All methods are pure functions."""

    # Currency symbols / prefixes to strip from values
    _CURRENCY_RE = re.compile(r"[₹$€£¥]")

    # Parenthetical negative: ``(1234)`` → ``-1234``
    _PAREN_NEG_RE = re.compile(r"^\((.+)\)$")

    # Characters to remove from labels (keep letters, digits, spaces, hyphens)
    _PUNCT_RE = re.compile(r"[^a-z0-9\s\-&]")

    # Collapse whitespace
    _MULTI_SPACE_RE = re.compile(r"\s+")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def normalize_label(self, raw: str) -> str:
        """Return the canonical-comparable form of a raw label string.

        Parameters
        ----------
        raw:
            The original column / row header as found in the source data.

        Returns
        -------
        str
            Cleaned label ready for matching.
        """
        text = raw.strip()
        text = text.lower()
        # Replace common unicode dashes with ASCII hyphen
        text = text.replace("–", "-").replace("—", "-")
        # Remove punctuation but keep '&' (e.g. "Reserves & Surplus")
        text = self._PUNCT_RE.sub("", text)
        text = self._MULTI_SPACE_RE.sub(" ", text).strip()

        logger.debug("normalize_label: %r → %r", raw, text)
        return text

    def normalize_value(self, raw: Any) -> Tuple[Optional[float], list[str]]:
        """Attempt to parse a numeric financial value.

        Handles:
        * String numbers with commas: ``"1,23,456"``
        * Currency prefixes: ``"₹12000"``
        * Parenthetical negatives: ``"(5000)"``
        * Already-numeric inputs (int / float)

        Returns
        -------
        tuple[float | None, list[str]]
            (parsed_value, list_of_warnings).  ``None`` if parsing fails.
        """
        warnings: list[str] = []

        if raw is None:
            warnings.append("Value is None")
            return None, warnings

        # Already numeric
        if isinstance(raw, (int, float)):
            return float(raw), warnings

        if not isinstance(raw, str):
            warnings.append(f"Unexpected value type: {type(raw).__name__}")
            return None, warnings

        text = raw.strip()
        if not text:
            warnings.append("Value is empty string")
            return None, warnings

        # Currency symbols
        text = self._CURRENCY_RE.sub("", text).strip()

        # Parenthetical negative
        m = self._PAREN_NEG_RE.match(text)
        if m:
            text = "-" + m.group(1)

        # Remove commas (Indian / Western formatting)
        text = text.replace(",", "")

        # Percent sign
        if text.endswith("%"):
            text = text[:-1].strip()
            warnings.append("Percent symbol stripped; raw value treated as number")

        try:
            value = float(text)
        except ValueError:
            warnings.append(f"Cannot parse numeric value from: {raw!r}")
            return None, warnings

        logger.debug("normalize_value: %r → %s (warnings=%s)", raw, value, warnings)
        return value, warnings

    def normalize_pair(
        self, raw_label: str, raw_value: Any
    ) -> Tuple[str, Optional[float], list[str]]:
        """Convenience: normalize both label and value in one call."""
        label = self.normalize_label(raw_label)
        value, warnings = self.normalize_value(raw_value)
        return label, value, warnings
