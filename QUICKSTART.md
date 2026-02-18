# Quick Start Guide — Financial Mapper Web Application

## 🌐 Access the Web Interface

The Flask web server is now running!

**Open your browser and navigate to:**
```
http://localhost:5000
```

## 📤 How to Use

### Step 1: Upload Your Balance Sheet

1. Click the **"Choose a file"** button on the homepage
2. Select a CSV or JSON file containing financial data
3. Click **"🚀 Analyze Balance Sheet"**

### Step 2: View Results

The results page shows:

✅ **Extracted Values** — All mapped financial fields with confidence scores

📊 **Financial Ratios** — Automatically calculated metrics across 5 categories:
- Liquidity Ratios (Current Ratio, Quick Ratio, Cash Ratio)
- Profitability Ratios (Net Margin, ROA, ROE, etc.)
- Leverage Ratios (Debt-to-Equity, Debt-to-Assets, etc.)
- Efficiency Ratios (Asset Turnover, Days Sales Outstanding, etc.)
- Coverage Ratios (Interest Coverage, Debt Service Coverage)

⚠️ **Warnings & Unmapped Fields** — Any labels that couldn't be matched

## 📁 Sample Files to Test

Two sample files are included in the `financial_mapper/data/` folder:

1. **sample_balance_sheet.csv** — 38 financial line items
2. **sample_balance_sheet.json** — 18 core fields

Try uploading these first to see how the system works!

## 🔧 API Access (Optional)

For programmatic access, use the JSON API:

```bash
curl -X POST -F "file=@path/to/balance_sheet.csv" \
  http://localhost:5000/api/parse
```

Returns JSON with extracted values and calculated ratios.

## 🛑 To Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

Or run:
```bash
# Find and kill the process
taskkill /F /IM python.exe
```

## 📖 Full Documentation

See [README.md](README.md) for complete API documentation and Python usage examples.

---

**Enjoy analyzing your financial data! 💰📈**
