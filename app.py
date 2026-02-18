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
from pathlib import Path
from typing import Any, Dict, Union
import tempfile

from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename

from financial_mapper.config import MatchingConfig, PipelineConfig, ValidationConfig
from financial_mapper.pipeline import FinancialMappingPipeline
from web.ratio_calculator import RatioCalculator

# ======================================================================
# Flask App Setup
# ======================================================================

app = Flask(__name__)
app.secret_key = "auditx-secret-key-change-in-production"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload
# Use /tmp for uploads in serverless environment (Vercel)
app.config["UPLOAD_FOLDER"] = Path("/tmp")

ALLOWED_EXTENSIONS = {"csv", "json", "txt", "xlsx", "xls"}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ======================================================================
# Pipeline Setup
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
calculator = RatioCalculator()


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
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    except Exception as e:
        logger.error(f"Error parsing file {filepath}: {e}")
        raise


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

    try:
        filename = secure_filename(file.filename)
        filepath = app.config["UPLOAD_FOLDER"] / filename
        file.save(filepath)

        year_results = parse_uploaded_file(filepath)
        
        # Check if multi-year or single-year result
        is_multi_year = len(year_results) > 1 or (len(year_results) == 1 and "single" not in year_results)
        
        if is_multi_year:
            # Multi-year: calculate ratios for each year
            all_ratios = {}
            all_mapped = {}
            for year, result in year_results.items():
                all_mapped[year] = result.mapped_dict()
                all_ratios[year] = calculator.calculate_all_ratios(all_mapped[year])
            
            filepath.unlink(missing_ok=True)
            
            return render_template(
                "results_multi_year.html",
                year_results=year_results,
                all_mapped=all_mapped,
                all_ratios=all_ratios,
                filename=filename,
                years=sorted(year_results.keys()),
            )
        else:
            # Single-year (legacy)
            result = year_results.get("single") or list(year_results.values())[0]
            mapped_data = result.mapped_dict()
            ratios = calculator.calculate_all_ratios(mapped_data)
            
            filepath.unlink(missing_ok=True)
            
            return render_template(
                "results.html",
                result=result,
                ratios=ratios,
                filename=filename,
            )

    except Exception as e:
        logger.exception("Error processing upload")
        flash(f"Error processing file: {str(e)}", "error")
        return redirect(url_for("index"))


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

        result = parse_uploaded_file(filepath)
        mapped_data = result.mapped_dict()
        ratios = calculator.calculate_all_ratios(mapped_data)

        filepath.unlink(missing_ok=True)

        return {
            "success": True,
            "extracted_values": mapped_data,
            "ratios": ratios,
            "mappings": [m.to_dict() for m in result.mappings],
            "unmapped": result.unmapped,
            "warnings": result.validation_warnings,
            "errors": result.validation_errors,
        }

    except Exception as e:
        logger.exception("API error")
        return {"error": str(e)}, 500


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
