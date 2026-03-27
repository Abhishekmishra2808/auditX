"""Hybrid mapping pipeline for balance-sheet analysis.

Flow:
extract -> normalize -> map_fields -> canonical dataset -> ratios
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from financial_mapper.config import PipelineConfig
from financial_mapper.excel_parser import ExcelParser
from financial_mapper.llm_hf import HuggingFaceMapper
from financial_mapper.logging_setup import configure_logging, get_logger
from financial_mapper.mapper import HybridFieldMapper, MapperConfig
from financial_mapper.ratio_engine import RatioEngine
from financial_mapper.schema import MappingResult, PipelineOutput
from financial_mapper.schema_builder import SchemaBuilder
from financial_mapper.validation import CanonicalValidator, ValidationConfigSimple

logger = get_logger("pipeline")


class FinancialMappingPipeline:
    """Orchestrates hybrid mapping and deterministic ratio calculation."""

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        extra_synonyms: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._config = config or PipelineConfig()

        configure_logging(level=self._config.log_level)

        self._llm = HuggingFaceMapper(
            model_id=self._config.llm.model_id,
            confidence_threshold=self._config.llm.confidence_threshold,
            timeout=self._config.llm.timeout,
            enabled=self._config.llm.enabled,
        )

        mapper_config = MapperConfig(
            fuzzy_threshold=self._config.matching.fuzzy_threshold,
            llm_enabled=self._config.llm.enabled,
        )
        self._mapper = HybridFieldMapper(
            config=mapper_config,
            llm_mapper=self._llm,
            extra_synonyms=extra_synonyms,
        )
        self._validator = CanonicalValidator(ValidationConfigSimple())
        self._ratio_engine = RatioEngine()

        logger.info(
            "Pipeline initialised — lookup_terms=%d, fuzzy_threshold=%.1f, "
            "llm_enabled=%s",
            self._mapper.synonym_count,
            self._config.matching.fuzzy_threshold,
            self._config.llm.enabled,
        )

    # ------------------------------------------------------------------ #
    # Convenience entry points (one per input format)
    # ------------------------------------------------------------------ #

    def map_dict(self, data: Dict[str, Any]) -> PipelineOutput:
        pairs = SchemaBuilder.read_dict(data)
        return self._run_pairs(pairs)

    def map_json(self, source: Union[str, Path]) -> PipelineOutput:
        pairs = SchemaBuilder.read_json(source)
        return self._run_pairs(pairs)

    def map_csv(self, source: Union[str, Path], label_col: int = 0, value_col: int = 1, has_header: bool = True) -> PipelineOutput:
        pairs = SchemaBuilder.read_csv(source, label_col, value_col, has_header)
        return self._run_pairs(pairs)

    def map_dataframe(self, df: Any) -> PipelineOutput:
        pairs = SchemaBuilder.read_dataframe(df)
        return self._run_pairs(pairs)

    def map_pairs(self, pairs: List[Tuple[str, Any]]) -> PipelineOutput:
        return self._run_pairs(pairs)

    def map_rows(self, rows: List[Dict[str, Any]]) -> PipelineOutput:
        extracted_fields: List[Dict[str, Any]] = []
        for row in rows:
            label = row.get("label") or row.get("name")
            if label is None:
                continue
            extracted_fields.append({"name": str(label), "value": row.get("value")})
        return self._run_extracted(extracted_fields)

    def map_excel(self, source: Union[str, Path], year_index: Optional[int] = None) -> Union[PipelineOutput, Dict[str, PipelineOutput]]:
        parser = ExcelParser(year_index=year_index)
        result = parser.parse_file(Path(source))

        if isinstance(result, dict):
            year_outputs: Dict[str, PipelineOutput] = {}
            for year, pairs in result.items():
                year_outputs[year] = self._run_pairs(pairs)
            return year_outputs
        return self._run_pairs(result)

    def map_with_ratios(self, extracted_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convenience API that returns canonical dataset plus computed ratios."""
        output = self._run_extracted(extracted_fields)
        canonical = {
            m.canonical_name: {"value": float(m.value), "confidence": float(m.confidence)}
            for m in output.mappings
            if m.value is not None
        }
        return {
            "canonical_dataset": canonical,
            "ratios": self._ratio_engine.calculate(canonical),
            "validation_warnings": output.validation_warnings,
        }

    def _run_pairs(self, pairs: List[Tuple[str, Any]]) -> PipelineOutput:
        extracted_fields = [{"name": label, "value": value} for label, value in pairs]
        return self._run_extracted(extracted_fields)

    def _run_extracted(self, extracted_fields: List[Dict[str, Any]]) -> PipelineOutput:
        canonical_dataset = self._mapper.map_fields(extracted_fields)
        validation_warnings = self._validator.validate(canonical_dataset)

        mappings = [
            MappingResult(
                canonical_name=canonical_name,
                raw_label=canonical_name,
                value=payload.get("value"),
                confidence=float(payload.get("confidence", 0.0)),
                match_method="hybrid",
                warnings=[],
            )
            for canonical_name, payload in canonical_dataset.items()
        ]

        logger.info(
            "Hybrid pipeline complete — extracted=%d, canonical=%d, warnings=%d",
            len(extracted_fields),
            len(mappings),
            len(validation_warnings),
        )

        return SchemaBuilder.build_output(
            mappings=mappings,
            unmapped=[],
            errors=[],
            warnings=validation_warnings,
        )

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #

    def add_synonyms(self, mapping: Dict[str, str]) -> None:
        """Hot-add synonyms after pipeline construction."""
        converted = {k: [v] if isinstance(v, str) else list(v) for k, v in mapping.items()}
        self._mapper.add_synonyms(converted)

    @property
    def synonym_count(self) -> int:
        return self._mapper.synonym_count
