"""
Unit tests for the SchemaBuilder (input readers & output assembly).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from financial_mapper.schema import MappingResult
from financial_mapper.schema_builder import SchemaBuilder


# ======================================================================
# Dict reader
# ======================================================================

class TestReadDict:
    def test_basic(self) -> None:
        pairs = SchemaBuilder.read_dict({"A": 1, "B": 2})
        assert pairs == [("A", 1), ("B", 2)]

    def test_empty(self) -> None:
        assert SchemaBuilder.read_dict({}) == []


# ======================================================================
# JSON reader
# ======================================================================

class TestReadJson:
    def test_object_json_string(self) -> None:
        raw = '{"Net Sales": 100, "Profit": 50}'
        pairs = SchemaBuilder.read_json(raw)
        assert len(pairs) == 2
        assert ("Net Sales", 100) in pairs

    def test_array_of_label_value(self) -> None:
        raw = json.dumps([
            {"label": "Sales", "value": 100},
            {"label": "Cost", "value": 50},
        ])
        pairs = SchemaBuilder.read_json(raw)
        assert len(pairs) == 2
        assert ("Sales", 100) in pairs

    def test_file_json(self, tmp_path: Path) -> None:
        data = {"X": 42}
        fp = tmp_path / "test.json"
        fp.write_text(json.dumps(data), encoding="utf-8")
        pairs = SchemaBuilder.read_json(fp)
        assert pairs == [("X", 42)]


# ======================================================================
# CSV reader
# ======================================================================

class TestReadCsv:
    def test_csv_string(self) -> None:
        csv_text = "Label,Value\nSales,1000\nCost,500\n"
        pairs = SchemaBuilder.read_csv(csv_text, has_header=True)
        assert len(pairs) == 2
        assert ("Sales", "1000") in pairs

    def test_csv_no_header(self) -> None:
        csv_text = "Sales,1000\nCost,500\n"
        pairs = SchemaBuilder.read_csv(csv_text, has_header=False)
        assert len(pairs) == 2

    def test_csv_file(self, tmp_path: Path) -> None:
        fp = tmp_path / "test.csv"
        fp.write_text("Label,Value\nA,10\nB,20\n", encoding="utf-8")
        pairs = SchemaBuilder.read_csv(fp)
        assert len(pairs) == 2


# ======================================================================
# Output assembly
# ======================================================================

class TestBuildOutput:
    def test_basic_assembly(self) -> None:
        m = MappingResult(
            canonical_name="Net Profit",
            raw_label="PAT",
            value=100_000,
            confidence=100.0,
            match_method="synonym",
        )
        output = SchemaBuilder.build_output(mappings=[m])
        assert output.success
        assert len(output.mappings) == 1
        assert output.mapped_dict() == {"Net Profit": 100_000}

    def test_to_json(self) -> None:
        m = MappingResult(
            canonical_name="Revenue",
            raw_label="Total Revenue",
            value=5_000_000,
            confidence=95.0,
            match_method="fuzzy",
        )
        output = SchemaBuilder.build_output(mappings=[m])
        j = SchemaBuilder.to_json(output)
        assert '"Revenue"' in j
        assert '"Total Revenue"' in j

    def test_to_csv_string(self) -> None:
        m = MappingResult(
            canonical_name="Tax",
            raw_label="Income Tax",
            value=30_000,
            confidence=100.0,
            match_method="synonym",
        )
        output = SchemaBuilder.build_output(mappings=[m])
        csv_str = SchemaBuilder.to_csv_string(output)
        assert "Tax" in csv_str
        assert "Income Tax" in csv_str
