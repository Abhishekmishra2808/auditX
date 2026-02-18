"""
Fuzzy Matching Layer.

When the synonym dictionary produces no hit, this layer uses ``rapidfuzz``
to find the closest canonical name.  Results are confidence-gated:

* Matches **below** ``fuzzy_threshold`` are rejected outright.
* If two candidates are within ``fuzzy_ambiguity_delta`` of each other the
  result is flagged as ambiguous — the pipeline will log a warning instead
  of silently picking one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rapidfuzz import fuzz, process

from financial_mapper.config import MatchingConfig
from financial_mapper.logging_setup import get_logger
from financial_mapper.schema import CANONICAL_NAMES

logger = get_logger("fuzzy_matcher")


@dataclass
class FuzzyCandidate:
    """A single candidate returned by the fuzzy matcher."""

    canonical_name: str
    score: float  # 0–100
    is_ambiguous: bool = False


class FuzzyMatcher:
    """Fuzzy-match a normalised label against the canonical schema.

    The matcher pre-builds a **lowercased** version of every canonical name
    so that comparisons are case-insensitive without needing to lower-case
    the (already normalised) input again at query time.

    Parameters
    ----------
    config:
        Matching thresholds and behaviour flags.
    extra_targets:
        Additional target strings to match against, beyond the canonical
        schema.  Useful for user-defined extensions.
    """

    def __init__(
        self,
        config: MatchingConfig,
        extra_targets: Optional[List[str]] = None,
    ) -> None:
        self._config = config

        # Build target pool: canonical_lower → canonical_original
        self._targets: dict[str, str] = {
            name.lower(): name for name in CANONICAL_NAMES
        }
        if extra_targets:
            for t in extra_targets:
                self._targets[t.lower()] = t

        # Pre-computed list for rapidfuzz ``process.extract``
        self._target_keys: list[str] = list(self._targets.keys())

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def match(self, normalised_label: str) -> Optional[FuzzyCandidate]:
        """Find the best canonical match for *normalised_label*.

        Returns
        -------
        FuzzyCandidate | None
            Best match above threshold, or ``None`` if nothing qualifies.
        """
        if not normalised_label:
            return None

        # Use token_sort_ratio — robust against word-order differences
        # (e.g. "profit net" vs "net profit").
        results = process.extract(
            normalised_label,
            self._target_keys,
            scorer=fuzz.token_sort_ratio,
            limit=5,
        )

        if not results:
            logger.debug("No fuzzy candidates for %r", normalised_label)
            return None

        best_key, best_score, _ = results[0]

        if best_score < self._config.fuzzy_threshold:
            logger.info(
                "Fuzzy best for %r is %r (%.1f) — below threshold %.1f; rejected",
                normalised_label,
                best_key,
                best_score,
                self._config.fuzzy_threshold,
            )
            return None

        # Ambiguity check: is the second-best dangerously close?
        is_ambiguous = False
        if len(results) > 1:
            _, second_score, _ = results[1]
            if best_score - second_score <= self._config.fuzzy_ambiguity_delta:
                is_ambiguous = True
                logger.warning(
                    "Ambiguous fuzzy match for %r: best=%r (%.1f), "
                    "runner-up=%r (%.1f) — delta %.1f ≤ %.1f",
                    normalised_label,
                    results[0][0],
                    best_score,
                    results[1][0],
                    second_score,
                    best_score - second_score,
                    self._config.fuzzy_ambiguity_delta,
                )

        canonical = self._targets[best_key]
        logger.info(
            "Fuzzy match: %r → %r (score=%.1f, ambiguous=%s)",
            normalised_label,
            canonical,
            best_score,
            is_ambiguous,
        )

        return FuzzyCandidate(
            canonical_name=canonical,
            score=best_score,
            is_ambiguous=is_ambiguous,
        )

    def match_batch(
        self, labels: List[str]
    ) -> dict[str, Optional[FuzzyCandidate]]:
        """Match multiple labels.  Returns ``{label: candidate}``."""
        return {label: self.match(label) for label in labels}
