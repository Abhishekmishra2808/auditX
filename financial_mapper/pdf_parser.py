"""
PDF Balance Sheet Parser.

Extracts financial data from PDF files, including:
- Tabular data from balance sheets
- Label-value pairs from structured text
- Multi-page documents
- Scanned PDFs with tabular regions

Uses pdfplumber to detect and parse tables, and falls back to
text extraction for unstructured content.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pdfplumber
from financial_mapper.logging_setup import get_logger

logger = get_logger("pdf_parser")


class PDFParser:
    """Parse financial data from PDF files."""

    @staticmethod
    def parse_file(filepath: Union[str, Path]) -> List[Tuple[str, Any]]:
        """
        Extract financial label-value pairs from a PDF file.

        Parameters
        ----------
        filepath : Union[str, Path]
            Path to the PDF file.

        Returns
        -------
        List[Tuple[str, Any]]
            List of (label, value) tuples extracted from the PDF.

        Raises
        ------
        ValueError
            If the file cannot be parsed or contains no extractable data.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"PDF file not found: {filepath}")

        pairs: List[Tuple[str, Any]] = []

        try:
            with pdfplumber.open(filepath) as pdf:
                logger.info(f"Parsing PDF: {filepath.name} ({len(pdf.pages)} pages)")

                for page_idx, page in enumerate(pdf.pages):
                    page_pairs = PDFParser._extract_from_page(page, page_idx)
                    pairs.extend(page_pairs)
                    logger.debug(
                        f"Page {page_idx + 1}: extracted {len(page_pairs)} pairs"
                    )

        except Exception as e:
            logger.error(f"Error parsing PDF {filepath}: {str(e)}")
            raise ValueError(
                f"Could not parse PDF file: {str(e)}"
            ) from e

        if not pairs:
            logger.warning(f"No financial data extracted from {filepath.name}")
            raise ValueError("PDF contains no extractable financial data")

        logger.info(f"PDF parsing complete: {len(pairs)} total pairs extracted")
        return pairs

    @staticmethod
    def _extract_from_page(
        page: pdfplumber.page.Page, page_idx: int
    ) -> List[Tuple[str, Any]]:
        """Extract label-value pairs from a single PDF page."""
        pairs: List[Tuple[str, Any]] = []

        try:
            # First try to extract tables
            tables = page.extract_tables()
            if tables:
                for table_idx, table in enumerate(tables):
                    table_pairs = PDFParser._extract_from_table(table)
                    pairs.extend(table_pairs)
                    logger.debug(
                        f"Page {page_idx + 1}, Table {table_idx + 1}: "
                        f"extracted {len(table_pairs)} pairs"
                    )

            # If no tables found, try text-based extraction
            if not pairs:
                text = page.extract_text()
                if text:
                    text_pairs = PDFParser._extract_from_text(text)
                    pairs.extend(text_pairs)
                    logger.debug(
                        f"Page {page_idx + 1} (text mode): "
                        f"extracted {len(text_pairs)} pairs"
                    )

        except Exception as e:
            logger.warning(f"Error extracting from page {page_idx + 1}: {str(e)}")

        return pairs

    @staticmethod
    def _extract_from_table(table: List[List[str]]) -> List[Tuple[str, Any]]:
        """Extract label-value pairs from a PDF table."""
        pairs: List[Tuple[str, Any]] = []
        
        # First pass: detect year columns in multi-year tables
        year_columns = PDFParser._detect_year_columns(table)

        for row_idx, row in enumerate(table):
            if not row or len(row) < 2:
                continue

            # Skip empty rows
            if all(not cell or not str(cell).strip() for cell in row):
                continue

            label_cell = str(row[0]).strip() if row[0] else ""
            if not label_cell:
                continue
            
            # Skip year header rows themselves
            if PDFParser._is_header_row(label_cell, str(row[1] if len(row) > 1 else "")):
                continue

            # If multi-year table detected, extract all year values
            if year_columns:
                for col_idx, year in year_columns:
                    if col_idx < len(row):
                        value_cell = str(row[col_idx]).strip() if row[col_idx] else ""
                        if value_cell:
                            value: Any = PDFParser._parse_value(value_cell)
                            if value is not None:
                                # Create pair with year in label
                                pairs.append((f"{label_cell} ({year})", value))
            else:
                # Single-year table: use right-most value
                value_cell = PDFParser._select_value_cell(row)
                if value_cell:
                    value: Any = PDFParser._parse_value(value_cell)
                    if value is not None:
                        pairs.append((label_cell, value))

        return pairs

    @staticmethod
    def _select_value_cell(row: List[Any]) -> str:
        """Select value cell from a row, preferring the right-most numeric token."""
        numeric_cells: List[str] = []
        for cell in row[1:]:
            if cell is None:
                continue
            text = str(cell).strip()
            if not text:
                continue
            if PDFParser._parse_value(text) is not None:
                numeric_cells.append(text)

        if numeric_cells:
            return numeric_cells[-1]

        # Fallback for malformed rows
        for cell in row[1:]:
            if cell is None:
                continue
            text = str(cell).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _detect_year_columns(table: List[List[str]]) -> List[Tuple[int, str]]:
        """
        Detect year columns in a multi-year table.
        
        Looks for year identifiers in the first row, which can be:
        - 4-digit years: "2025", "2026"
        - Date formats: "31-03-2025", "2025-03-31", etc.
        - Full dates: "31-03-2026", "2026"
        
        Returns
        -------
        List[Tuple[int, str]]
            List of (column_index, year) tuples for columns containing years.
            Empty list if single-year or unparseable table.
        """
        year_columns: List[Tuple[int, str]] = []
        
        if not table or not table[0]:
            return year_columns
        
        # Check first row for year identifiers (skip first column which is usually labels)
        first_row = table[0]
        for col_idx in range(1, len(first_row)):  # Start from column 1
            cell = first_row[col_idx]
            if cell is None:
                continue
            
            text = str(cell).strip()
            if not text:
                continue
            
            # Check for 4-digit year patterns: 2025, 2026, etc.
            year_match = re.search(r"\d{4}", text)
            if year_match:
                year_str = year_match.group()
                year_columns.append((col_idx, year_str))
        
        # Sort by column index to maintain left-to-right order
        year_columns.sort(key=lambda x: x[0])
        return year_columns

    @staticmethod
    def _extract_from_text(text: str) -> List[Tuple[str, Any]]:
        """
        Extract label-value pairs from unstructured PDF text.

        Looks for patterns like:
        - Label: 12345
        - Label 12345
        - Label    12345
        """
        pairs: List[Tuple[str, Any]] = []

        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Pattern 1: "Label: value"
            match = re.match(r"^([A-Za-z\s&()]+?):\s*([-\d,.\s]+)$", line)
            if match:
                label, value_str = match.groups()
                label = label.strip()
                value = PDFParser._parse_value(value_str.strip())
                if value is not None and label:
                    pairs.append((label, value))
                    continue

            # Pattern 2: "Label" followed by whitespace and number
            match = re.match(r"^([A-Za-z\s&()]+?)\s{2,}([-\d,.\s]+)$", line)
            if match:
                label, value_str = match.groups()
                label = label.strip()
                value = PDFParser._parse_value(value_str.strip())
                if value is not None and label:
                    pairs.append((label, value))

        return pairs

    @staticmethod
    def _is_header_row(label: str, value: str) -> bool:
        """Check if row looks like a header, not data."""
        header_keywords = [
            "sr no",
            "serial",
            "field",
            "particulars",
            "description",
            "item",
            "label",
            "amount",
            "value",
            "as on",
            "as at",
            "for the year",
            "balance sheet",
            "profit and loss",
            "statement",
            "rupees",
            "rs.",
            "₹",
            "currency",
        ]

        label_lower = label.lower()
        value_lower = value.lower()

        # Skip rows where first column looks like data (not header)
        # but allow section headers like "I. EQUITY AND LIABILITIES"
        if label_lower.startswith(("i.", "ii.", "iii.", "iv.", "a)", "b)", "c)", "d)")):
            # These are section/subsection headers, could be real sections
            # Don't skip them - check other criteria
            pass

        # Skip pure numeric year rows (e.g., just "2025")
        if re.fullmatch(r"\d{4}", value_lower):
            return True

        return any(kw in label_lower or kw in value_lower for kw in header_keywords)

    @staticmethod
    def _parse_value(value_str: str) -> Any:
        """
        Parse a string value into a numeric or string type.

        Handles:
        - Numeric values with commas, parentheses, currency symbols
        - Returns None for non-numeric strings
        """
        if not value_str or not str(value_str).strip():
            return None

        value_str = str(value_str).strip()

        # Remove currency symbols, percent signs, and spaces
        cleaned = re.sub(r"[₹$€£%\s]", "", value_str)

        # Handle parenthetical negatives
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]

        # Remove commas
        cleaned = cleaned.replace(",", "")

        # Try to parse as float
        try:
            result = float(cleaned)
            return result if result != 0 or cleaned != "0" else result
        except ValueError:
            # Return as string if not numeric
            return value_str if value_str else None
