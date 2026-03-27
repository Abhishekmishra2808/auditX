"""
auditX — Financial Statement Analysis Engine.

A Flask web interface for uploading balance sheets (CSV, JSON, XLSX),
parsing them, extracting standardised financial values, and calculating
key financial ratios.

Run with: python app.py
Then navigate to: http://localhost:5000
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Union
import tempfile

from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Load .env file for API keys when python-dotenv is available.
if load_dotenv is not None:
    load_dotenv()

from financial_mapper.config import MatchingConfig, PipelineConfig, ValidationConfig
from financial_mapper.pipeline import FinancialMappingPipeline
from financial_mapper.hierarchy_builder import build_hierarchy, flatten_hierarchy
from financial_mapper.aggregator import compute_aggregates
from financial_mapper.pdf_parser import PDFParser
from financial_mapper.gstin_validator import validate_gstin, get_gst_portal_url, format_gstin_display
from financial_mapper.gst_searcher import search_gst_async, GSTDetails
from financial_mapper.schema_builder import SchemaBuilder
from financial_mapper.llm_ratio_calculator import LLMRatioCalculator
from web.ratio_calculator import RatioCalculator

# ======================================================================
# Flask App Setup
# ======================================================================

app = Flask(__name__)
app.secret_key = "auditx-secret-key-change-in-production"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload
# Use temp directory for uploads (works on both Windows and Unix)
app.config["UPLOAD_FOLDER"] = Path(tempfile.gettempdir())

ALLOWED_EXTENSIONS = {"csv", "json", "txt", "xlsx", "xls", "pdf"}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ======================================================================
# Pipeline & Calculator Setup
# ======================================================================

pipeline_config = PipelineConfig(
    matching=MatchingConfig(
        fuzzy_threshold=75.0,
        fuzzy_ambiguity_delta=5.0,
        strict_mode=False,
    ),
    validation=ValidationConfig(
        required_fields=[],
        error_on_duplicate=False,
    ),
    log_level=logging.WARNING,
)

pipeline = FinancialMappingPipeline(config=pipeline_config)
ratio_calculator = RatioCalculator()
llm_ratio_calculator = LLMRatioCalculator()


# ======================================================================
# Helper Functions
# ======================================================================

def allowed_file(filename: str) -> bool:
    """Check if the uploaded file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_uploaded_file(filepath: Path) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Parse an uploaded file and extract financial data.
    
    Returns
    -------
    For single-year files: Dict with single result
    For multi-year files: Dict mapping years to results
    """
    ext = filepath.suffix.lower()

    try:
        if ext == ".csv":
            result = pipeline.map_csv(filepath)
            return {"single": result}
        elif ext == ".json":
            result = pipeline.map_json(filepath)
            return {"single": result}
        elif ext in (".xlsx", ".xls"):
            # Use multi-year mode (year_index=None)
            result = pipeline.map_excel(filepath, year_index=None)
            # Check if multi-year or single-year result
            if isinstance(result, dict) and all(isinstance(v, type(result[list(result.keys())[0]])) for v in result.values()):
                # Multi-year result
                return result
            else:
                # Single-year result (backwards compatibility)
                return {"single": result}
        elif ext == ".txt":
            try:
                result = pipeline.map_csv(filepath)
            except Exception:
                result = pipeline.map_json(filepath)
            return {"single": result}
        elif ext == ".pdf":
            pairs = PDFParser.parse_file(filepath)
            result = pipeline.map_pairs(pairs)
            return {"single": result}
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    except Exception as e:
        logger.error(f"Error parsing file {filepath}: {e}")
        raise


def _filter_present_values(mapped_data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields with usable numeric values."""
    filtered: Dict[str, Any] = {}
    for key, value in mapped_data.items():
        if key.startswith("_"):
            continue
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        filtered[key] = value
    return filtered


def _pairs_to_raw_terms(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
    """Convert extracted pairs to display-friendly raw terms dict.

    If a label appears multiple times, values are summed when numeric.
    """
    raw_terms: Dict[str, Any] = {}
    for label, value in pairs:
        if label not in raw_terms:
            raw_terms[label] = value
            continue

        prev = raw_terms[label]
        if isinstance(prev, (int, float)) and isinstance(value, (int, float)):
            raw_terms[label] = float(prev) + float(value)
        else:
            raw_terms[label] = value
    return raw_terms


def _build_raw_terms_year_matrix(
    pairs: List[tuple[str, Any]],
) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Build a matrix: field_name -> {year -> value} from labels like 'Field (2026)'."""
    pattern = re.compile(r"^(.*?)\s*\((\d{4})\)$")

    years_seen: set[str] = set()
    field_order: List[str] = []
    matrix: Dict[str, Dict[str, Any]] = {}

    for label, value in pairs:
        match = pattern.match(str(label).strip())
        if not match:
            continue

        base_field = match.group(1).strip()
        year = match.group(2)

        if base_field not in matrix:
            matrix[base_field] = {}
            field_order.append(base_field)

        matrix[base_field][year] = value
        years_seen.add(year)

    if not years_seen:
        return [], {}

    years = sorted(years_seen)
    ordered_matrix = {field: matrix[field] for field in field_order}
    return years, ordered_matrix


def _build_raw_terms_by_year(
    years: List[str],
    raw_terms_matrix: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Transpose field-wise matrix into year-wise raw term dictionaries."""
    by_year: Dict[str, Dict[str, Any]] = {year: {} for year in years}

    for field_name, yearly_values in raw_terms_matrix.items():
        for year in years:
            if year not in yearly_values:
                continue
            value = yearly_values[year]
            if isinstance(value, (int, float)):
                by_year[year][field_name] = float(value)

    return by_year


def _enrich_and_compute_ratios(
    result,
    rows: Union[List[Dict[str, Any]], None] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply aggregation to mapped result and compute ratios deterministically.

    Parameters
    ----------
    result:
        PipelineOutput from the mapping pipeline.
    rows:
        Optional original rows (used to build hierarchy for aggregation).

    Returns
    -------
    tuple[mapped_values_dict, ratios_dict]
    """
    # Get canonical mapped values
    mapped_data = result.mapped_dict()

    # Build hierarchy from rows for aggregation (if rows available)
    if rows:
        tree = build_hierarchy(rows)
        enriched = compute_aggregates(tree, mapped_data)
        enriched.pop("_aggregation_warnings", None)
    else:
        enriched = dict(mapped_data)

    # Filter to usable values only
    clean = _filter_present_values(enriched)

    # Compute ratios deterministically from canonical fields
    ratios = ratio_calculator.calculate_all_ratios(clean)

    return clean, ratios


# ======================================================================
# Routes
# ======================================================================

@app.route("/")
def index():
    """Landing page with upload form."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle file upload and redirect to results."""
    if "file" not in request.files:
        flash("No file uploaded", "error")
        return redirect(url_for("index"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash(
            f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            "error",
        )
        return redirect(url_for("index"))

    # Handle GSTIN (optional)
    gstin = request.form.get("gstin", "").strip()
    gstin_valid = False
    gstin_formatted = None
    gstin_portal_url = None
    gst_message = None

    if gstin:
        is_valid, validation_msg = validate_gstin(gstin)
        if is_valid:
            gstin_valid = True
            gstin_formatted = format_gstin_display(gstin)
            gstin_portal_url = get_gst_portal_url(gstin)
            gst_message = "Valid GSTIN format. You can verify this GSTIN on the official GST portal."
        else:
            flash(f"Invalid GSTIN: {validation_msg}", "warning")
            gst_message = validation_msg

    try:
        filename = secure_filename(file.filename)
        filepath = app.config["UPLOAD_FOLDER"] / filename
        file.save(filepath)

        ext = filepath.suffix.lower()

        if ext in (".xlsx", ".xls"):
            # --- Multi-year Excel flow ---
            from financial_mapper.excel_parser import ExcelParser
            parser = ExcelParser(year_index=None)
            raw_result = parser.parse_file(filepath)

            if isinstance(raw_result, dict):
                # Multi-year: raw_result = {year: [(label, value), ...]}
                all_canonical = {}
                all_raw_terms = {}
                all_ratios = {}
                for year, pairs in raw_result.items():
                    rows = [{"label": lbl, "value": val} for lbl, val in pairs]
                    yr_result = pipeline.map_rows(rows)
                    canonical, ratios = _enrich_and_compute_ratios(yr_result, rows)
                    all_canonical[year] = canonical
                    all_raw_terms[year] = _pairs_to_raw_terms(pairs)
                    all_ratios[year] = ratios

                    logger.info(
                        "Year %s: %d raw terms, %d canonical fields, %d ratio categories",
                        year, len(all_raw_terms[year]), len(canonical), len(ratios)
                    )

                filepath.unlink(missing_ok=True)
                return render_template(
                    "results_multi_year_new.html",
                    year_results={
                        yr: type("R", (), {
                            "mappings": [],
                            "unmapped": [],
                            "mapped_dict": lambda c=canonical: c,
                        })()
                        for yr, canonical in all_canonical.items()
                    },
                    all_raw_terms=all_raw_terms,
                    all_ratios=all_ratios,
                    filename=filename,
                    years=sorted(all_canonical.keys()),
                    gstin=gstin_formatted,
                    gstin_valid=gstin_valid,
                    gstin_portal_url=gstin_portal_url,
                    gst_message=gst_message,
                )
            else:
                # Single-year from Excel
                pairs = raw_result
                rows = [{"label": lbl, "value": val} for lbl, val in pairs]
                result = pipeline.map_rows(rows)
                canonical, ratios = _enrich_and_compute_ratios(result, rows)
                raw_terms = _pairs_to_raw_terms(pairs)
                filepath.unlink(missing_ok=True)
                return render_template(
                    "results_new.html",
                    result=result,
                    ratios=ratios,
                    raw_terms=raw_terms,
                    filename=filename,
                    gstin=gstin_formatted,
                    gstin_valid=gstin_valid,
                    gstin_portal_url=gstin_portal_url,
                    gst_message=gst_message,
                )

        else:
            # --- CSV / JSON / PDF / TXT flow (flat mapping, single year) ---
            if ext == ".csv" or ext == ".txt":
                pairs = SchemaBuilder.read_csv(filepath)
                result = pipeline.map_pairs(pairs)
            elif ext == ".json":
                pairs = SchemaBuilder.read_json(filepath)
                result = pipeline.map_pairs(pairs)
            elif ext == ".pdf":
                pairs = PDFParser.parse_file(filepath)
                result = pipeline.map_pairs(pairs)
            else:
                raise ValueError(f"Unsupported file type: {ext}")

            raw_terms = _pairs_to_raw_terms(pairs)
            raw_years, raw_terms_matrix = _build_raw_terms_year_matrix(pairs)
            yearly_ratios: Dict[str, Dict[str, Any]] = {}
            if raw_years and raw_terms_matrix:
                raw_terms_by_year = _build_raw_terms_by_year(raw_years, raw_terms_matrix)
                for idx, year in enumerate(raw_years):
                    previous_period = raw_terms_by_year.get(raw_years[idx - 1]) if idx > 0 else None
                    yearly_ratios[year] = llm_ratio_calculator.calculate_all_ratios(
                        raw_terms_by_year.get(year, {}),
                        previous_period=previous_period,
                    )

            _canonical, ratios = _enrich_and_compute_ratios(result)
            filepath.unlink(missing_ok=True)
            return render_template(
                "results_new.html",
                result=result,
                ratios=ratios,
                yearly_ratios=yearly_ratios,
                raw_terms=raw_terms,
                raw_years=raw_years,
                raw_terms_matrix=raw_terms_matrix,
                filename=filename,
                gstin=gstin_formatted,
                gstin_valid=gstin_valid,
                gstin_portal_url=gstin_portal_url,
                gst_message=gst_message,
            )

    except Exception as e:
        logger.exception("Error processing upload")
        flash(f"Error processing file: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/validate_gstin", methods=["POST"])
def validate_gstin_route():
    """API endpoint to validate GSTIN and get portal link."""
    gstin = request.form.get("gstin", "").strip()

    if not gstin:
        return {"valid": False, "message": "GSTIN cannot be empty"}, 400

    is_valid, validation_msg = validate_gstin(gstin)

    if is_valid:
        formatted = format_gstin_display(gstin)
        portal_url = get_gst_portal_url(gstin)
        return {
            "valid": True,
            "message": validation_msg,
            "formatted": formatted,
            "portal_url": portal_url,
        }
    else:
        return {"valid": False, "message": validation_msg}, 400


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """JSON API endpoint for programmatic access."""
    if "file" not in request.files:
        return {"error": "No file uploaded"}, 400

    file = request.files["file"]

    if not allowed_file(file.filename):
        return {"error": "Invalid file type"}, 400

    try:
        filename = secure_filename(file.filename)
        filepath = app.config["UPLOAD_FOLDER"] / filename
        file.save(filepath)

        ext = filepath.suffix.lower()

        if ext in (".xlsx", ".xls"):
            from financial_mapper.excel_parser import ExcelParser
            parser = ExcelParser(year_index=None)
            raw_result = parser.parse_file(filepath)

            if isinstance(raw_result, dict):
                by_year = {}
                for year, pairs in raw_result.items():
                    rows = [{"label": lbl, "value": val} for lbl, val in pairs]
                    yr_result = pipeline.map_rows(rows)
                    canonical, ratios = _enrich_and_compute_ratios(yr_result, rows)
                    by_year[year] = {
                        "raw_extracted_terms": canonical,
                        "ratios": ratios,
                        "mappings": [m.to_dict() for m in yr_result.mappings],
                        "unmapped": yr_result.unmapped,
                    }
                payload = {"success": True, "by_year": by_year}
            else:
                pairs = raw_result
                rows = [{"label": lbl, "value": val} for lbl, val in pairs]
                result = pipeline.map_rows(rows)
                canonical, ratios = _enrich_and_compute_ratios(result, rows)
                payload = {
                    "success": True,
                    "raw_extracted_terms": canonical,
                    "ratios": ratios,
                    "mappings": [m.to_dict() for m in result.mappings],
                    "unmapped": result.unmapped,
                }
        else:
            if ext in (".csv", ".txt"):
                result = pipeline.map_csv(filepath)
            elif ext == ".json":
                result = pipeline.map_json(filepath)
            elif ext == ".pdf":
                pairs = PDFParser.parse_file(filepath)
                result = pipeline.map_pairs(pairs)
            else:
                raise ValueError(f"Unsupported file type: {ext}")

            canonical, ratios = _enrich_and_compute_ratios(result)
            payload = {
                "success": True,
                "raw_extracted_terms": canonical,
                "ratios": ratios,
                "mappings": [m.to_dict() for m in result.mappings],
                "unmapped": result.unmapped,
            }

        filepath.unlink(missing_ok=True)
        return payload

    except Exception as e:
        logger.exception("API error")
        return {"error": str(e)}, 500


# ======================================================================
# GST Search Routes (Separate Feature)
# ======================================================================

@app.route("/search-gst", methods=["GET"])
def search_gst_page():
    """Display GST search form."""
    return render_template("gst_search.html")


@app.route("/search-gst", methods=["POST"])
def search_gst():
    """Handle GST search request."""
    gstin = request.form.get("gstin", "").strip().upper()
    search_mode = request.form.get("search_mode", "auto").lower()

    if not gstin:
        flash("Please enter a GSTIN", "error")
        return redirect(url_for("search_gst_page"))

    # Validate format first
    is_valid, validation_msg = validate_gstin(gstin)
    if not is_valid:
        return render_template(
            "gst_search.html",
            error=f"Invalid GSTIN format: {validation_msg}"
        )

    logger.info(f"Searching GST for: {gstin} (mode: {search_mode})")
    
    # Determine if manual CAPTCHA mode
    manual_captcha = search_mode == "manual"
    
    if manual_captcha:
        flash("Opening browser for manual CAPTCHA entry. Please complete CAPTCHA and click SEARCH on the portal.", "info")
    else:
        flash("Searching GST portal... This may take a minute.", "info")

    try:
        # Search the GST portal
        result = search_gst_async(gstin, timeout=60, manual_captcha=manual_captcha)
        
        if result.error:
            logger.warning(f"GST search completed with error: {result.error}")

        return render_template(
            "gst_search.html",
            result=result,
            search_mode=search_mode
        )

    except Exception as e:
        logger.exception(f"Error searching GST: {e}")
        return render_template(
            "gst_search.html",
            error=f"Search failed: {str(e)}",
            search_mode=search_mode
        )


# ======================================================================
# Main
# ======================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  auditX — Financial Statement Analysis Engine")
    print("=" * 70)
    print(f"  URL: http://localhost:5000")
    print(f"  Synonym count: {pipeline.synonym_count}")
    print("=" * 70 + "\n")

    app.run(debug=True, host="0.0.0.0", port=5000)

# ======================================================================
# Vercel Serverless Handler
# ======================================================================

# Export the Flask app for Vercel
handler = app
