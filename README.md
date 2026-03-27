# Financial Mapper

Financial Mapper is a Flask + Python pipeline that extracts financial values from uploaded statements, normalizes them to canonical fields, and calculates ratios.

This project is now sheet-aware by design with LLM as the primary semantic matcher:

- **LLM-First Matching**: LLM understands financial terminology semantically first (after synonyms)
- It shows only fields that actually exist in the uploaded sheet.
- It calculates only ratios that can be computed from available inputs.
- It skips missing-data ratios safely instead of showing noisy N/A blocks.

## Matching Order (New)

1. **Normalize** - Handle spacing, currency, formatting
2. **Synonym** - Exact known mappings (100% confidence)
3. **LLM** - Semantic understanding of financial fields (primary layer)  ← NEW
4. **Fuzzy** - Fallback for typos and word variations
5. **Unmapped** - Fields not handled by any layer

The LLM engine semantically understands financial concepts, so you get better matches for domain-specific terminology that fuzzy matching alone cannot handle.

## What It Does

1. Upload a statement file (CSV, JSON, XLSX, XLS).
2. Parse labels and values from the sheet.
3. Map labels to canonical financial fields (synonym, fuzzy, optional LLM fallback).
4. Display only present extracted fields.
5. Compute and display only computable ratios for that exact sheet.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Input Formats

- CSV
- JSON
- XLSX/XLS (single-year and multi-year)

## Core Behavior (Robust Mode)

- Missing fields do not break processing.
- Empty/None values are excluded from visible extracted output.
- Ratios are filtered to only those with valid computed values.
- API response follows the same filtering rules as UI.

## Project Layout

- app.py: Flask routes, upload flow, parsed output preparation
- financial_mapper/pipeline.py: mapping orchestrator
- web/ratio_calculator.py: ratio engine with computable-ratio filtering
- templates/results.html: single-year results view
- templates/results_multi_year.html: multi-year comparison view

## Run Tests

```bash
pytest tests -v
```

## Notes

- Keep configuration in .env for API keys and runtime settings.
- Do not create additional markdown reports for routine changes.
- Update this README when behavior changes.
    "Another Label": "Current Assets",
})
```

**JSON File:**
```json
{
  "my custom label": "Net Profit",
  "another label": "Current Assets"
}
```

```python
from pathlib import Path
config = PipelineConfig(
    custom_synonym_path=Path("path/to/synonyms.json")
)
```

### Semantic Matching Layer

The pipeline includes a hook for embedding-based semantic matching. Implement `_semantic_match()` in [pipeline.py](financial_mapper/pipeline.py) to integrate sentence-transformers or OpenAI embeddings.

## 📄 License

This project is provided as-is for educational and commercial use.

## 👥 Author

Built with precision for financial data extraction and analysis.

---

**Need help?** Check the examples folder or run the test suite for comprehensive usage patterns.
