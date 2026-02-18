"""
Pipeline Orchestrator.

The central entry point that wires together every layer:

    Raw Data  →  Normalizer  →  Synonym Mapper  →  Fuzzy Matcher
              →  (optional) Semantic Matcher  →  Validator  →  Output

Usage
-----
>>> from financial_mapper.pipeline import FinancialMappingPipeline
>>> from financial_mapper.config import PipelineConfig
>>>
>>> pipe = FinancialMappingPipeline(PipelineConfig())
>>> result = pipe.map_dict({"Profit After Tax": 500000})
>>> print(result.to_dict())
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from financial_mapper.config import PipelineConfig
from financial_mapper.excel_parser import ExcelParser
from financial_mapper.fuzzy_matcher import FuzzyMatcher
from financial_mapper.logging_setup import configure_logging, get_logger
from financial_mapper.normalizer import LabelNormalizer
from financial_mapper.schema import MappingResult, PipelineOutput
from financial_mapper.schema_builder import SchemaBuilder
from financial_mapper.synonym_mapper import SynonymMapper
from financial_mapper.validator import Validator

logger = get_logger("pipeline")


class FinancialMappingPipeline:
    """Orchestrates the full label-mapping pipeline.

    Parameters
    ----------
    config:
        All tuneable knobs.  Defaults are sane for most balance-sheet data.
    extra_synonyms:
        Additional synonym mappings to merge into the built-in dictionary.
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        extra_synonyms: Optional[Dict[str, str]] = None,
    ) -> None:
        self._config = config or PipelineConfig()

        # Bootstrap logging before anything else
        configure_logging(level=self._config.log_level)

        # Construct layers
        self._normalizer = LabelNormalizer()
        self._synonyms = SynonymMapper(
            normalizer=self._normalizer,
            extra_synonyms=extra_synonyms,
        )
        self._fuzzy = FuzzyMatcher(config=self._config.matching)
        self._validator = Validator(config=self._config.validation)
        self._builder = SchemaBuilder()

        # Load custom synonym file if specified
        if self._config.custom_synonym_path:
            self._synonyms.load_custom_synonyms(self._config.custom_synonym_path)

        logger.info(
            "Pipeline initialised — synonyms=%d, fuzzy_threshold=%.1f, "
            "strict=%s",
            self._synonyms.size,
            self._config.matching.fuzzy_threshold,
            self._config.matching.strict_mode,
        )

    # ------------------------------------------------------------------ #
    # Convenience entry points (one per input format)
    # ------------------------------------------------------------------ #

    def map_dict(self, data: Dict[str, Any]) -> PipelineOutput:
        """Map a plain Python dictionary."""
        pairs = SchemaBuilder.read_dict(data)
        return self._run(pairs)

    def map_json(self, source: Union[str, Path]) -> PipelineOutput:
        """Map from a JSON file path or JSON string."""
        pairs = SchemaBuilder.read_json(source)
        return self._run(pairs)

    def map_csv(
        self,
        source: Union[str, Path],
        label_col: int = 0,
        value_col: int = 1,
        has_header: bool = True,
    ) -> PipelineOutput:
        """Map from a CSV file or CSV string."""
        pairs = SchemaBuilder.read_csv(source, label_col, value_col, has_header)
        return self._run(pairs)

    def map_dataframe(self, df: Any) -> PipelineOutput:
        """Map from a pandas DataFrame."""
        pairs = SchemaBuilder.read_dataframe(df)
        return self._run(pairs)

    def map_pairs(self, pairs: List[Tuple[str, Any]]) -> PipelineOutput:
        """Map from a pre-built list of ``(label, value)`` tuples."""
        return self._run(pairs)

    def map_excel(
        self,
        source: Union[str, Path],
        year_index: Optional[int] = None,
    ) -> Union[PipelineOutput, Dict[str, PipelineOutput]]:
        """Map from an Excel (.xlsx) file.

        Automatically detects sheet layouts including Schedule III,
        T-account (Dr/Cr), and generic two-column formats.

        Parameters
        ----------
        source:
            Path to the .xlsx file.
        year_index:
            When multiple year-columns exist, which one to use (0-based).
            If None, extracts ALL years and returns a dict mapping years to outputs.
        
        Returns
        -------
        PipelineOutput if year_index is specified
        Dict[str, PipelineOutput] if year_index is None (multi-year mode)
        """
        parser = ExcelParser(year_index=year_index)
        result = parser.parse_file(Path(source))
        
        # Check if result is multi-year (dict) or single-year (list)
        if isinstance(result, dict):
            # Multi-year mode: process each year separately
            year_outputs = {}
            for year, pairs in result.items():
                year_outputs[year] = self._run(pairs)
                logger.info("Processed year '%s': %d mappings, %d unmapped", 
                          year, len(year_outputs[year].mappings), len(year_outputs[year].unmapped))
            return year_outputs
        else:
            # Single-year mode (backwards compatibility)
            return self._run(result)

    # ------------------------------------------------------------------ #
    # Core pipeline logic
    # ------------------------------------------------------------------ #

    def _run(self, pairs: List[Tuple[str, Any]]) -> PipelineOutput:
        """Execute the full mapping pipeline on raw (label, value) pairs."""
        mappings: list[MappingResult] = []
        unmapped: list[dict[str, Any]] = []
        seen_canonical: dict[str, str] = {}  # canonical → raw_label (conflict check)

        for raw_label, raw_value in pairs:
            result = self._map_single(raw_label, raw_value, seen_canonical)
            if result is not None:
                mappings.append(result)
            else:
                unmapped.append({"raw_label": raw_label, "raw_value": raw_value})

        # Validation pass
        report = self._validator.validate(mappings)

        output = SchemaBuilder.build_output(
            mappings=mappings,
            unmapped=unmapped,
            errors=report.errors,
            warnings=report.warnings,
        )

        logger.info(
            "Pipeline complete — mapped=%d, unmapped=%d, errors=%d, warnings=%d",
            len(mappings),
            len(unmapped),
            len(report.errors),
            len(report.warnings),
        )

        if self._config.matching.strict_mode and not output.success:
            raise RuntimeError(
                f"Strict mode: pipeline produced {len(report.errors)} "
                f"validation error(s):\n" + "\n".join(report.errors)
            )

        return output

    def _map_single(
        self,
        raw_label: str,
        raw_value: Any,
        seen_canonical: dict[str, str],
    ) -> Optional[MappingResult]:
        """Map one (label, value) pair through the matching layers."""
        warnings: list[str] = []

        # --- Step 1: Normalise ----------------------------------------
        norm_label, value, value_warnings = self._normalizer.normalize_pair(
            raw_label, raw_value
        )
        warnings.extend(value_warnings)

        # --- Step 2: Synonym lookup -----------------------------------
        canonical = self._synonyms.lookup(norm_label)
        if canonical is not None:
            return self._build_result(
                canonical_name=canonical,
                raw_label=raw_label,
                value=value,
                confidence=100.0,
                method="synonym",
                warnings=warnings,
                seen_canonical=seen_canonical,
            )

        # --- Step 3: Fuzzy match --------------------------------------
        candidate = self._fuzzy.match(norm_label)
        if candidate is not None:
            if candidate.is_ambiguous:
                warnings.append(
                    f"Ambiguous fuzzy match for '{raw_label}' → "
                    f"'{candidate.canonical_name}' "
                    f"(score={candidate.score:.1f})"
                )
            return self._build_result(
                canonical_name=candidate.canonical_name,
                raw_label=raw_label,
                value=value,
                confidence=candidate.score,
                method="fuzzy",
                warnings=warnings,
                seen_canonical=seen_canonical,
            )

        # --- Step 4: Semantic match (optional) ------------------------
        if self._config.enable_semantic_layer:
            semantic_result = self._semantic_match(norm_label)
            if semantic_result is not None:
                can_name, score = semantic_result
                return self._build_result(
                    canonical_name=can_name,
                    raw_label=raw_label,
                    value=value,
                    confidence=score * 100,
                    method="semantic",
                    warnings=warnings,
                    seen_canonical=seen_canonical,
                )

        # --- No match -------------------------------------------------
        logger.warning("UNMAPPED: %r (normalised=%r)", raw_label, norm_label)
        return None

    def _build_result(
        self,
        *,
        canonical_name: str,
        raw_label: str,
        value: Any,
        confidence: float,
        method: str,
        warnings: list[str],
        seen_canonical: dict[str, str],
    ) -> MappingResult:
        """Create a ``MappingResult`` and check for duplicate canonical mappings."""
        # Conflict detection
        if canonical_name in seen_canonical:
            prev = seen_canonical[canonical_name]
            conflict_msg = (
                f"Duplicate mapping to '{canonical_name}': "
                f"previously mapped from '{prev}', now also from '{raw_label}'"
            )
            warnings.append(conflict_msg)
            logger.warning(conflict_msg)
        else:
            seen_canonical[canonical_name] = raw_label

        logger.info(
            "MAPPED: %r → '%s' [%s] confidence=%.1f",
            raw_label,
            canonical_name,
            method,
            confidence,
        )

        return MappingResult(
            canonical_name=canonical_name,
            raw_label=raw_label,
            value=value,
            confidence=confidence,
            match_method=method,
            warnings=warnings.copy(),
        )

    # ------------------------------------------------------------------ #
    # Semantic matching stub
    # ------------------------------------------------------------------ #

    @staticmethod
    def _semantic_match(
        normalised_label: str,
    ) -> Optional[Tuple[str, float]]:
        """Hook for embedding-based semantic matching.

        This is a **placeholder** — integrate your own embedding model
        (e.g. sentence-transformers, OpenAI embeddings) here.

        Returns
        -------
        tuple[str, float] | None
            ``(canonical_name, cosine_similarity)`` or ``None``.
        """
        logger.debug(
            "Semantic layer called for %r — not implemented; returning None",
            normalised_label,
        )
        return None

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #

    def add_synonyms(self, mapping: Dict[str, str]) -> None:
        """Hot-add synonyms after pipeline construction."""
        self._synonyms.add_synonyms(mapping)

    @property
    def synonym_count(self) -> int:
        return self._synonyms.size
