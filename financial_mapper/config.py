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
class PipelineConfig:
    """Top-level configuration aggregating all sub-configs."""

    matching: MatchingConfig = field(default_factory=MatchingConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    # Logging level for the mapping audit trail
    log_level: int = logging.INFO

    # Optional path to a user-supplied synonym JSON file that is *merged*
    # with the built-in dictionary.
    custom_synonym_path: Optional[Path] = None

    # When True, the optional semantic matching layer is activated.
    enable_semantic_layer: bool = False
