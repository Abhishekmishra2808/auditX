"""
Financial Ratio Calculator.

Computes standard financial ratios and metrics from standardised balance sheet
and income statement data.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


class RatioCalculator:
    """Calculate financial ratios from mapped canonical data."""

    @staticmethod
    def safe_divide(
        numerator: Optional[float],
        denominator: Optional[float],
        default: Optional[float] = None,
    ) -> Optional[float]:
        """Safely divide two numbers, returning None if invalid."""
        if numerator is None or denominator is None:
            return default
        if denominator == 0:
            return default
        result = numerator / denominator
        if math.isnan(result) or math.isinf(result):
            return default
        return result

    def calculate_all_ratios(
        self, data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate all available ratios from the provided data.

        Returns a nested dict grouped by category:
        {
            "Liquidity": {...},
            "Profitability": {...},
            "Leverage": {...},
            ...
        }
        """
        return {
            "Liquidity": self._liquidity_ratios(data),
            "Profitability": self._profitability_ratios(data),
            "Leverage": self._leverage_ratios(data),
            "Efficiency": self._efficiency_ratios(data),
            "Coverage": self._coverage_ratios(data),
        }

    def _liquidity_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate liquidity ratios."""
        ca = data.get("Current Assets")
        cl = data.get("Current Liabilities")
        inventory = data.get("Inventory") or data.get("Closing Inventory")
        cash = data.get("Cash and Cash Equivalents")

        current_ratio = self.safe_divide(ca, cl)
        quick_ratio = self.safe_divide((ca - inventory) if ca and inventory else ca, cl)
        cash_ratio = self.safe_divide(cash, cl)

        return {
            "Current Ratio": {
                "value": current_ratio,
                "formula": "Current Assets / Current Liabilities",
                "interpretation": "Measures ability to pay short-term obligations",
            },
            "Quick Ratio": {
                "value": quick_ratio,
                "formula": "(Current Assets - Inventory) / Current Liabilities",
                "interpretation": "Ability to meet short-term obligations with liquid assets",
            },
            "Cash Ratio": {
                "value": cash_ratio,
                "formula": "Cash & Equivalents / Current Liabilities",
                "interpretation": "Most conservative liquidity measure",
            },
        }

    def _profitability_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate profitability ratios."""
        net_profit = data.get("Net Profit")
        gross_profit = data.get("Gross Profit")
        ebitda = data.get("EBITDA")
        operating_profit = data.get("Operating Profit")
        revenue = data.get("Revenue") or data.get("Net Sales") or data.get("Net Revenue")
        total_assets = data.get("Total Assets")
        equity = data.get("Equity") or data.get("Net Worth")
        cogs = data.get("Cost of Goods Sold")

        net_margin = self.safe_divide(net_profit, revenue)
        gross_margin = self.safe_divide(gross_profit, revenue)
        ebitda_margin = self.safe_divide(ebitda, revenue)
        operating_margin = self.safe_divide(operating_profit, revenue)
        roa = self.safe_divide(net_profit, total_assets)
        roe = self.safe_divide(net_profit, equity)

        return {
            "Net Profit Margin": {
                "value": net_margin,
                "percentage": net_margin * 100 if net_margin else None,
                "formula": "Net Profit / Revenue × 100",
                "interpretation": "Profit earned per dollar of revenue",
            },
            "Gross Profit Margin": {
                "value": gross_margin,
                "percentage": gross_margin * 100 if gross_margin else None,
                "formula": "Gross Profit / Revenue × 100",
                "interpretation": "Profitability after direct costs",
            },
            "EBITDA Margin": {
                "value": ebitda_margin,
                "percentage": ebitda_margin * 100 if ebitda_margin else None,
                "formula": "EBITDA / Revenue × 100",
                "interpretation": "Operating profitability before financing effects",
            },
            "Operating Margin": {
                "value": operating_margin,
                "percentage": operating_margin * 100 if operating_margin else None,
                "formula": "Operating Profit / Revenue × 100",
                "interpretation": "Efficiency of core operations",
            },
            "Return on Assets (ROA)": {
                "value": roa,
                "percentage": roa * 100 if roa else None,
                "formula": "Net Profit / Total Assets × 100",
                "interpretation": "How efficiently assets generate profit",
            },
            "Return on Equity (ROE)": {
                "value": roe,
                "percentage": roe * 100 if roe else None,
                "formula": "Net Profit / Equity × 100",
                "interpretation": "Return generated on shareholder investment",
            },
        }

    def _leverage_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate leverage/solvency ratios."""
        total_debt = data.get("Total Debt")
        lt_debt = data.get("Long-term Borrowings") or data.get("Long-term Liabilities")
        equity = data.get("Equity") or data.get("Net Worth")
        total_assets = data.get("Total Assets")
        ebitda = data.get("EBITDA")

        debt_to_equity = self.safe_divide(total_debt, equity)
        debt_to_assets = self.safe_divide(total_debt, total_assets)
        equity_ratio = self.safe_divide(equity, total_assets)
        debt_to_ebitda = self.safe_divide(total_debt, ebitda)

        return {
            "Debt-to-Equity": {
                "value": debt_to_equity,
                "formula": "Total Debt / Equity",
                "interpretation": "Financial leverage — higher means more debt",
            },
            "Debt-to-Assets": {
                "value": debt_to_assets,
                "percentage": debt_to_assets * 100 if debt_to_assets else None,
                "formula": "Total Debt / Total Assets × 100",
                "interpretation": "Percentage of assets financed by debt",
            },
            "Equity Ratio": {
                "value": equity_ratio,
                "percentage": equity_ratio * 100 if equity_ratio else None,
                "formula": "Equity / Total Assets × 100",
                "interpretation": "Percentage of assets owned by shareholders",
            },
            "Debt-to-EBITDA": {
                "value": debt_to_ebitda,
                "formula": "Total Debt / EBITDA",
                "interpretation": "Years needed to repay debt with operating cash",
            },
        }

    def _efficiency_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate efficiency/activity ratios."""
        revenue = data.get("Revenue") or data.get("Net Sales") or data.get("Net Revenue")
        total_assets = data.get("Total Assets")
        fixed_assets = data.get("Fixed Assets") or data.get("Tangible Assets")
        cogs = data.get("Cost of Goods Sold")
        inventory = data.get("Inventory") or data.get("Closing Inventory")
        receivables = data.get("Trade Receivables") or data.get("Closing Debtors")
        payables = data.get("Trade Payables")
        working_capital = data.get("Working Capital")
        ca = data.get("Current Assets")
        cl = data.get("Current Liabilities")

        # Calculate working capital if not provided
        if working_capital is None and ca is not None and cl is not None:
            working_capital = ca - cl

        asset_turnover = self.safe_divide(revenue, total_assets)
        fixed_asset_turnover = self.safe_divide(revenue, fixed_assets)
        inventory_turnover = self.safe_divide(cogs, inventory)
        receivables_turnover = self.safe_divide(revenue, receivables)
        payables_turnover = self.safe_divide(cogs, payables)
        working_capital_turnover = self.safe_divide(revenue, working_capital)

        # Convert turnovers to days
        days_inventory = self.safe_divide(365, inventory_turnover) if inventory_turnover else None
        days_receivables = self.safe_divide(365, receivables_turnover) if receivables_turnover else None
        days_payables = self.safe_divide(365, payables_turnover) if payables_turnover else None

        return {
            "Asset Turnover": {
                "value": asset_turnover,
                "formula": "Revenue / Total Assets",
                "interpretation": "Revenue generated per dollar of assets",
            },
            "Fixed Asset Turnover": {
                "value": fixed_asset_turnover,
                "formula": "Revenue / Fixed Assets",
                "interpretation": "Efficiency of fixed asset utilization",
            },
            "Inventory Turnover": {
                "value": inventory_turnover,
                "days": days_inventory,
                "formula": "COGS / Inventory",
                "interpretation": "How quickly inventory is sold",
            },
            "Receivables Turnover": {
                "value": receivables_turnover,
                "days": days_receivables,
                "formula": "Revenue / Receivables",
                "interpretation": "How quickly receivables are collected",
            },
            "Days Sales Outstanding (DSO)": {
                "value": days_receivables,
                "formula": "365 / Receivables Turnover",
                "interpretation": "Average days to collect payment",
            },
            "Days Inventory Outstanding (DIO)": {
                "value": days_inventory,
                "formula": "365 / Inventory Turnover",
                "interpretation": "Average days inventory is held",
            },
            "Days Payables Outstanding (DPO)": {
                "value": days_payables,
                "formula": "365 / Payables Turnover",
                "interpretation": "Average days to pay suppliers",
            },
            "Working Capital Turnover": {
                "value": working_capital_turnover,
                "formula": "Revenue / Working Capital",
                "interpretation": "Efficiency of working capital usage",
            },
        }

    def _coverage_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate coverage ratios."""
        ebitda = data.get("EBITDA")
        operating_profit = data.get("Operating Profit")
        net_profit = data.get("Net Profit")
        interest = data.get("Interest")
        total_debt = data.get("Total Debt")
        loan_installment = data.get("Loan Installment")

        interest_coverage = self.safe_divide(ebitda or operating_profit, interest)
        debt_service_coverage = self.safe_divide(
            ebitda,
            (interest + loan_installment) if interest and loan_installment else None,
        )

        return {
            "Interest Coverage": {
                "value": interest_coverage,
                "formula": "EBITDA / Interest Expense",
                "interpretation": "Ability to cover interest payments",
            },
            "Debt Service Coverage": {
                "value": debt_service_coverage,
                "formula": "EBITDA / (Interest + Principal)",
                "interpretation": "Ability to service total debt obligations",
            },
        }
