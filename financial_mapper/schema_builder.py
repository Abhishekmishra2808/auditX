"""
Schema Builder.

Responsible for constructing the final standardised output from a list of
``MappingResult`` objects.  Acts as the "assembler" that downstream ratio
calculators consume.

Also supports reading raw data from multiple formats (CSV, JSON, dict,
pandas DataFrame) into a uniform ``list[tuple[str, Any]]`` representation
that the pipeline can iterate over.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from financial_mapper.logging_setup import get_logger
from financial_mapper.schema import MappingResult, PipelineOutput

logger = get_logger("schema_builder")


class SchemaBuilder:
    """Builds and serialises the final standardised financial schema."""

    # ------------------------------------------------------------------ #
    # Input readers — produce [ (raw_label, raw_value), ... ]
    # ------------------------------------------------------------------ #

    @staticmethod
    def read_dict(data: Dict[str, Any]) -> List[Tuple[str, Any]]:
        """Read from a plain Python dict."""
        return list(data.items())

    @staticmethod
    def read_json(source: Union[str, Path]) -> List[Tuple[str, Any]]:
        """Read from a JSON file or JSON string.

        Supports two shapes:
        * Object ``{"label": value, ...}``
        * Array of objects ``[{"label": "...", "value": ...}, ...]``
        """
        if isinstance(source, Path) or (
            isinstance(source, str) and not source.lstrip().startswith(("{", "["))
        ):
            path = Path(source)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(source)

        if isinstance(data, dict):
            return list(data.items())

        if isinstance(data, list):
            pairs: List[Tuple[str, Any]] = []
            for item in data:
                if isinstance(item, dict) and "label" in item and "value" in item:
                    pairs.append((item["label"], item["value"]))
                elif isinstance(item, dict):
                    # Fallback: treat first key→value pair
                    for k, v in item.items():
                        pairs.append((k, v))
                else:
                    logger.warning("Skipping unrecognised JSON array element: %r", item)
            return pairs

        raise ValueError(f"Unsupported JSON root type: {type(data).__name__}")

    @staticmethod
    def read_csv(
        source: Union[str, Path],
        label_col: int = 0,
        value_col: int = 1,
        has_header: bool = True,
    ) -> List[Tuple[str, Any]]:
        """Read from a CSV file or CSV string.

        Parameters
        ----------
        source:
            File path or raw CSV text.
        label_col:
            Column index for labels (default 0).
        value_col:
            Column index for values (default 1).
        has_header:
            When True the first row is skipped.
        """
        if isinstance(source, Path) or (
            isinstance(source, str) and "\n" not in source and Path(source).exists()
        ):
            with open(Path(source), encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
        else:
            reader = csv.reader(StringIO(source))
            rows = list(reader)

        if has_header and rows:
            rows = rows[1:]

        pairs: List[Tuple[str, Any]] = []
        for row in rows:
            if len(row) > max(label_col, value_col):
                pairs.append((row[label_col].strip(), row[value_col].strip()))
            else:
                logger.warning("Skipping short CSV row: %r", row)
        return pairs

    @staticmethod
    def read_dataframe(df: Any) -> List[Tuple[str, Any]]:
        """Read from a pandas DataFrame.

        Expects either:
        * Two columns — first is label, second is value.
        * Or columns named ``label`` / ``value`` (case-insensitive).
        """
        try:
            import pandas as pd  # noqa: F811
        except ImportError as exc:
            raise ImportError(
                "pandas is required to use read_dataframe"
            ) from exc

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")

        cols_lower = {c.lower(): c for c in df.columns}
        if "label" in cols_lower and "value" in cols_lower:
            label_series = df[cols_lower["label"]]
            value_series = df[cols_lower["value"]]
        elif len(df.columns) >= 2:
            label_series = df.iloc[:, 0]
            value_series = df.iloc[:, 1]
        else:
            raise ValueError(
                "DataFrame must have at least two columns or columns named "
                "'label' and 'value'"
            )

        return list(zip(label_series.astype(str), value_series))

    # ------------------------------------------------------------------ #
    # Output assembly
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_output(
        mappings: List[MappingResult],
        unmapped: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> PipelineOutput:
        """Assemble the final ``PipelineOutput``."""
        return PipelineOutput(
            mappings=mappings,
            unmapped=unmapped or [],
            validation_errors=errors or [],
            validation_warnings=warnings or [],
        )

    @staticmethod
    def to_json(output: PipelineOutput, indent: int = 2) -> str:
        """Serialise ``PipelineOutput`` to a JSON string."""
        return json.dumps(output.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def to_csv_string(output: PipelineOutput) -> str:
        """Serialise mappings to CSV text (excludes unmapped / validation)."""
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "canonical_name", "raw_label", "value",
            "confidence", "match_method", "warnings",
        ])
        for m in output.mappings:
            writer.writerow([
                m.canonical_name,
                m.raw_label,
                m.value,
                round(m.confidence, 2),
                m.match_method,
                "; ".join(m.warnings) if m.warnings else "",
            ])
        return buf.getvalue()
