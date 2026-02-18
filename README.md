# Financial Mapper — Semantic Balance Sheet Extraction Engine

A production-grade Python system that reads balance sheet data with inconsistent column names and maps all values to a standardized financial schema for ratio calculations.

## 🎯 Key Features

- **Semantic Matching**: Understands 200+ financial label variations (e.g., "PAT" → "Net Profit")
- **Fuzzy Matching**: Handles typos and word-order variations using `rapidfuzz`
- **Confidence Scoring**: Every mapping returns a 0-100 confidence score
- **Multi-format Support**: CSV, JSON, pandas DataFrame, Python dict
- **Financial Ratios**: Automatically calculates 30+ financial ratios and metrics
- **Auditable**: Complete logging trail for all mapping decisions
- **Extensible**: Add custom synonyms at runtime or via JSON files

## 🚀 Quick Start

### Installation

```bash
# Clone or download this repository
cd "AANYA GOYAL"

# Create virtual environment (optional but recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Web Application

The easiest way to use Financial Mapper is through the web interface:

```bash
python app.py
```

Then open your browser to: **http://localhost:5000**

Upload a CSV or JSON file containing balance sheet data and get:
- Extracted and standardized financial values
- Confidence scores for each mapping
- 30+ calculated financial ratios
- Liquidity, profitability, leverage, and efficiency metrics

### Python API

Use the pipeline programmatically:

```python
from financial_mapper.pipeline import FinancialMappingPipeline

# Initialize pipeline
pipeline = FinancialMappingPipeline()

# Map from dictionary
data = {
    "Profit After Tax": 500_000,
    "Owner Funds": 1_200_000,
    "Current Assets": 3_450_000,
    "Total Current Liabilities": 2_100_000,
}

result = pipeline.map_dict(data)

# Get standardized values
mapped = result.mapped_dict()
print(mapped["Net Profit"])     # 500000.0
print(mapped["Net Worth"])       # 1200000.0
print(mapped["Current Assets"])  # 3450000.0

# Inspect confidence
for m in result.mappings:
    print(f"{m.canonical_name}: {m.confidence}% via {m.match_method}")
```

### Supported Input Formats

**CSV:**
```csv
Label,Value
Profit After Tax,500000
Current Assets,3450000
Net Sales,4200000
```

**JSON:**
```json
{
  "Profit After Tax": 500000,
  "Current Assets": 3450000,
  "Net Sales": 4200000
}
```

**pandas DataFrame:**
```python
import pandas as pd
df = pd.DataFrame({
    "label": ["Net Sales", "Net Profit"],
    "value": [4200000, 500000]
})
result = pipeline.map_dataframe(df)
```

## 📊 Canonical Schema

The system maps to these standard financial fields:

**Balance Sheet:**
- Current Assets, Current Liabilities
- Long-term Borrowings, Long-term Liabilities
- Share Capital, Reserves & Surplus
- Fixed Assets, Intangible Assets
- Working Capital, Net Worth

**Income Statement:**
- Net Sales, Revenue, Gross Profit
- Operating Expenses, EBITDA
- Net Profit, Tax, Interest
- Cost of Goods Sold

**Cash Flow & Others:**
- Cash and Cash Equivalents
- Trade Receivables, Trade Payables
- Inventory, Depreciation

See [schema.py](financial_mapper/schema.py) for the full list.

## 🧮 Calculated Ratios

The system automatically computes:

**Liquidity:**
- Current Ratio, Quick Ratio, Cash Ratio

**Profitability:**
- Net Profit Margin, Gross Margin, EBITDA Margin
- ROA, ROE, Operating Margin

**Leverage:**
- Debt-to-Equity, Debt-to-Assets
- Equity Ratio, Debt-to-EBITDA

**Efficiency:**
- Asset Turnover, Inventory Turnover
- Days Sales Outstanding (DSO)
- Days Inventory Outstanding (DIO)

**Coverage:**
- Interest Coverage, Debt Service Coverage

## 🔧 Configuration

Customize behavior via `PipelineConfig`:

```python
from financial_mapper.config import (
    PipelineConfig,
    MatchingConfig,
    ValidationConfig
)

config = PipelineConfig(
    matching=MatchingConfig(
        fuzzy_threshold=80.0,      # Minimum fuzzy match score
        fuzzy_ambiguity_delta=5.0, # Flag ambiguous if <5 points apart
        strict_mode=False,          # Raise on validation errors
    ),
    validation=ValidationConfig(
        required_fields=["Net Profit", "Current Assets"],
        error_on_duplicate=True,
    ),
)

pipeline = FinancialMappingPipeline(config)
```

## 📁 Project Structure

```
financial_mapper/
├── __init__.py           # Package entry point
├── config.py             # All tuneable parameters
├── logging_setup.py      # Audit trail logging
├── schema.py             # Canonical field definitions
├── normalizer.py         # Label preprocessing
├── synonym_mapper.py     # Dictionary-based matching
├── fuzzy_matcher.py      # Fuzzy string matching
├── validator.py          # Post-mapping validation
├── schema_builder.py     # Input/output handling
├── pipeline.py           # Main orchestrator
└── data/
    ├── custom_synonyms.json
    ├── sample_balance_sheet.csv
    └── sample_balance_sheet.json

web/
├── __init__.py
└── ratio_calculator.py   # Financial ratio engine

templates/
├── base.html
├── index.html            # Upload page
└── results.html          # Analysis results

static/
└── style.css             # Web interface styles

tests/
├── test_normalizer.py
├── test_synonym_mapper.py
├── test_fuzzy_matcher.py
├── test_validator.py
├── test_schema_builder.py
└── test_pipeline.py

app.py                    # Flask web server
```

## 🧪 Running Tests

```bash
pytest tests/ -v
```

All 70 tests should pass.

## 📝 Examples

See [examples/run_example.py](financial_mapper/examples/run_example.py):

```bash
python financial_mapper/examples/run_example.py
```

Demonstrates:
- Dictionary input mapping
- CSV file parsing
- JSON file parsing
- Ratio calculation workflow

## 🔐 Safety & Correctness

- **Never guesses silently** — low-confidence matches are flagged
- **Ambiguity detection** — warns when multiple candidates are close
- **Duplicate prevention** — detects if two labels map to same field
- **Validation layer** — checks required fields, numeric sanity
- **Full audit trail** — every decision is logged

## 🛠️ Extending the System

### Add Custom Synonyms

**Runtime:**
```python
pipeline.add_synonyms({
    "My Custom Label": "Net Profit",
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
