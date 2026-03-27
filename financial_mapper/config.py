"""
Configuration module for Financial Mapper.

All tuneable parameters — thresholds, paths, feature flags — live here.
Nothing is hard-coded in business logic modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class MatchingConfig:
    """Controls matching behaviour across all layers."""

    # Fuzzy matching: minimum similarity score (0–100) to accept a match
    fuzzy_threshold: float = 80.0

    # Fuzzy matching: if two candidates are within this delta of each other,
    # treat the result as ambiguous and flag a conflict.
    fuzzy_ambiguity_delta: float = 5.0

    # Semantic / embedding layer threshold (0.0–1.0 cosine similarity)
    semantic_threshold: float = 0.85

    # When True the pipeline will raise on any unresolved mapping instead of
    # returning partial results.
    strict_mode: bool = False


@dataclass(frozen=True)
class ValidationConfig:
    """Controls the validation layer."""

    # Canonical fields that *must* be present for the output to be considered
    # valid.  An empty list disables the check.
    required_fields: list[str] = field(default_factory=list)

    # Maximum allowed absolute value — catches obvious unit errors
    max_absolute_value: float = 1e15

    # When True, duplicates trigger an error; when False, a warning.
    error_on_duplicate: bool = True


@dataclass(frozen=True)
class LLMConfig:
    """Controls LLM-based fallback mapping layer."""

    # When True, LLM fallback is available and called for unresolved terms
    enabled: bool = True

    # Hugging Face model identifier (with provider suffix for router endpoint)
    model_id: str = "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai"

    # Minimum confidence (0.0–1.0) for LLM mappings to be accepted
    confidence_threshold: float = 0.75

    # HTTP timeout for HF API calls (seconds)
    timeout: int = 20

    # When True, rejected LLM mappings (low confidence or invalid concept)
    # are still logged but do not produce mapping results
    log_rejected: bool = True


@dataclass(frozen=True)
class HierarchyConfig:
    """Controls hierarchy building and aggregation behaviour."""

    # Keywords that identify section headers in balance sheets (lowercased).
    # If empty, falls back to defaults in hierarchy_builder.py.
    section_keywords: list[str] = field(default_factory=list)

    # Prefix used to detect total rows (e.g. "Total Current Assets").
    total_prefix: str = "Total"

    # Relative tolerance for children-sum vs stated-total cross-checks.
    # abs(computed - stated) / stated <= tolerance is acceptable.
    aggregation_tolerance: float = 0.01


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level configuration aggregating all sub-configs."""

    matching: MatchingConfig = field(default_factory=MatchingConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    hierarchy: HierarchyConfig = field(default_factory=HierarchyConfig)

    # Logging level for the mapping audit trail
    log_level: int = logging.INFO

    # Optional path to a user-supplied synonym JSON file that is *merged*
    # with the built-in dictionary.
    custom_synonym_path: Optional[Path] = None

    # When True, the optional semantic matching layer is activated.
    enable_semantic_layer: bool = False
