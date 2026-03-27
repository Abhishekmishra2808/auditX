"""Hybrid field mapper: dictionary -> fuzzy -> LLM fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from rapidfuzz import fuzz, process

from financial_mapper.llm_hf import HuggingFaceMapper
from financial_mapper.logging_setup import get_logger
from financial_mapper.normalizer import normalize, to_float
from financial_mapper.synonyms import DEFAULT_ALLOWED_FIELDS, build_lookup

logger = get_logger("mapper")

FUZZY_THRESHOLD_DEFAULT = 85.0
LLM_FALLBACK_CONFIDENCE = 0.7


@dataclass(frozen=True)
class MapperConfig:
    """Configuration for hybrid mapper behavior."""

    fuzzy_threshold: float = FUZZY_THRESHOLD_DEFAULT
    llm_enabled: bool = True
    allowed_fields: tuple[str, ...] = DEFAULT_ALLOWED_FIELDS


class HybridFieldMapper:
    """Map extracted financial terms into canonical fields with minimal LLM usage."""

    def __init__(
        self,
        config: Optional[MapperConfig] = None,
        llm_mapper: Optional[HuggingFaceMapper] = None,
        extra_synonyms: Optional[Dict[str, Iterable[str]]] = None,
    ) -> None:
        self.config = config or MapperConfig()
        self._lookup = build_lookup(extra_synonyms=extra_synonyms)
        self._llm = llm_mapper
        self._llm_cache: Dict[tuple[str, ...], Dict[str, str]] = {}

    @property
    def synonym_count(self) -> int:
        return len(self._lookup)

    def add_synonyms(self, mapping: Dict[str, Iterable[str]]) -> None:
        """Extend mapper synonym lookup at runtime."""
        additions = build_lookup(extra_synonyms=mapping)
        self._lookup.update(additions)

    def map_fields(self, extracted_fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """Map extracted fields to canonical dataset.

        Each input item must contain:
        {"name": str, "value": float}

        Returns:
        {
          "cash": {"value": 11670.0, "confidence": 1.0},
          ...
        }
        """
        canonical: Dict[str, Dict[str, float]] = {}
        unmatched: List[Tuple[str, str, float]] = []

        for field in extracted_fields:
            raw_name = str(field.get("name", ""))
            value = to_float(field.get("value"))
            if not raw_name or value is None:
                continue

            normalized_name = normalize(raw_name)
            exact_match = self._lookup.get(normalized_name)
            if exact_match:
                self._merge(canonical, exact_match, value, 1.0)
            else:
                unmatched.append((raw_name, normalized_name, value))

        remaining: List[Tuple[str, str, float]] = []
        choices = list(self._lookup.keys())

        for raw_name, normalized_name, value in unmatched:
            best = process.extractOne(normalized_name, choices, scorer=fuzz.WRatio)
            if best and float(best[1]) >= self.config.fuzzy_threshold:
                matched_term = str(best[0])
                score = float(best[1]) / 100.0
                self._merge(canonical, self._lookup[matched_term], value, score)
            else:
                remaining.append((raw_name, normalized_name, value))

        if remaining and self.config.llm_enabled and self._llm and self._llm.enabled:
            llm_input = [item[0] for item in remaining]
            llm_mappings = self._batch_llm_map(llm_input)

            for raw_name, _normalized_name, value in remaining:
                llm_target = llm_mappings.get(raw_name)
                if llm_target is None:
                    continue
                self._merge(canonical, llm_target, value, LLM_FALLBACK_CONFIDENCE)

        return canonical

    def _batch_llm_map(self, raw_terms: List[str]) -> Dict[str, str]:
        """Call LLM at most once per unique term set and cache the response."""
        cache_key = tuple(sorted(raw_terms))
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        prompt_map = self._llm.map_to_canonical(
            labels=raw_terms,
            candidates=list(self.config.allowed_fields),
        )

        # Enforce one-to-one mapping from raw terms to canonical targets.
        assigned: Dict[str, str] = {}
        used_targets: set[str] = set()
        allowed_lookup = {
            normalize(field).replace(" ", "_"): field
            for field in self.config.allowed_fields
        }
        for raw_term in raw_terms:
            target = prompt_map.get(raw_term)
            if target is None:
                continue

            normalized_target = normalize(str(target)).replace(" ", "_")
            resolved_target = allowed_lookup.get(normalized_target)
            if resolved_target is None:
                continue
            if resolved_target in used_targets:
                continue
            used_targets.add(resolved_target)
            assigned[raw_term] = resolved_target

        self._llm_cache[cache_key] = assigned
        logger.info(
            "Batch LLM fallback mapped %d/%d unmatched terms",
            len(assigned),
            len(raw_terms),
        )
        return assigned

    @staticmethod
    def _merge(
        canonical: Dict[str, Dict[str, float]],
        key: str,
        value: float,
        confidence: float,
    ) -> None:
        """Merge mapped values by summing duplicates and keeping max confidence."""
        existing = canonical.get(key)
        if existing is None:
            canonical[key] = {"value": float(value), "confidence": float(confidence)}
            return

        existing["value"] += float(value)
        existing["confidence"] = max(existing["confidence"], float(confidence))


_DEFAULT_MAPPER = HybridFieldMapper()


def map_fields(extracted_fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Functional entrypoint for mapping extracted fields."""
    return _DEFAULT_MAPPER.map_fields(extracted_fields)
