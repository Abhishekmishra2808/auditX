"""Normalization helpers for balance-sheet labels and values."""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

_SPACE_RE = re.compile(r"\s+")
_CURRENCY_RE = re.compile(r"[₹$€£¥]")
_PAREN_NEG_RE = re.compile(r"^\((.+)\)$")


def normalize(text: str) -> str:
    """Normalize raw labels for matching.

    Rules:
    - lowercase
    - replace '-', '/', ':' with spaces
    - remove extra spaces
    - strip
    """
    normalized = text.lower()
    normalized = normalized.replace("-", " ").replace("/", " ").replace(":", " ")
    normalized = _SPACE_RE.sub(" ", normalized)
    return normalized.strip()


def to_float(raw: Any) -> Optional[float]:
    """Convert a raw value to float, returning None when parsing fails."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    text = _CURRENCY_RE.sub("", text).strip()
    paren_neg = _PAREN_NEG_RE.match(text)
    if paren_neg:
        text = f"-{paren_neg.group(1)}"

    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()

    try:
        return float(text)
    except ValueError:
        return None


class LabelNormalizer:
    """Backward-compatible wrapper used by older pipeline components."""

    def normalize_label(self, raw: str) -> str:
        return normalize(raw)

    def normalize_value(self, raw: Any) -> Tuple[Optional[float], list[str]]:
        value = to_float(raw)
        if value is None:
            return None, [f"Cannot parse numeric value from: {raw!r}"]
        return value, []

    def normalize_pair(self, raw_label: str, raw_value: Any) -> Tuple[str, Optional[float], list[str]]:
        label = self.normalize_label(raw_label)
        value, warnings = self.normalize_value(raw_value)
        return label, value, warnings
