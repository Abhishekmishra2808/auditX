"""Key financial indicator calculator with dictionary-first term selection.

Selection order:
1) Dictionary/keyword deterministic matching
2) LLM fallback only when dictionary matching fails
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional, Tuple

from financial_mapper.llm_hf import HuggingFaceMapper
from financial_mapper.logging_setup import get_logger

logger = get_logger("llm_ratio_calculator")


class LLMRatioCalculator:
    """Calculate financial ratios using LLM-driven term selection."""

    _VARIABLE_TERM_KEYWORDS: Dict[str, list[str]] = {
        "current assets": [
            "total current assets",
            "current assets",
        ],
        "current liabilities": [
            "total current liabilities",
            "current liabilities",
        ],
        "inventory": [
            "inventories",
            "inventory",
            "finished goods",
            "stock",
        ],
        "net sales": [
            "net sales",
            "sales",
            "revenue",
            "turnover",
        ],
        "ebitda": [
            "ebitda",
            "ebidta",
            "operating profit",
            "earnings before interest tax depreciation amortization",
        ],
        "net profit": [
            "net profit",
            "profit",
            "profit after tax",
            "pat",
        ],
        "depreciation": [
            "depreciation",
            "depreciation and amortization",
        ],
        "amortization": [
            "amortization",
            "depreciation and amortization",
        ],
        "revenue": [
            "revenue",
            "sales",
            "turnover",
            "total income",
        ],
        "sales": [
            "sales",
            "revenue",
            "turnover",
        ],
        "gross profit": [
            "gross profit",
        ],
        "total debt": [
            "total debt",
            "total liabilities",
            "borrowings",
            "debt",
        ],
        "equity": [
            "total equity",
            "shareholders funds",
            "shareholder funds",
            "reserves and surplus",
            "share capital",
            "equity",
            "net worth",
        ],
        "net worth": [
            "net worth",
            "equity",
            "shareholders funds",
            "shareholder funds",
        ],
        "total assets": [
            "total assets",
        ],
        "total liabilities": [
            "total liabilities",
            "liabilities",
        ],
        "term liabilities": [
            "term liabilities",
            "non current liabilities",
            "non-current liabilities",
            "long-term liabilities",
            "long term liabilities",
        ],
        "reserves and surplus": [
            "reserves and surplus",
            "reserves",
            "surplus",
        ],
        "share capital": [
            "share capital",
            "paid up capital",
            "equity share capital",
        ],
    }

    def __init__(self):
        self.llm = HuggingFaceMapper()
        self.llm_selections: Dict[str, Dict[str, str]] = {}  # ratio_name -> {formula_var: raw_term}
        self._selection_cache: Dict[tuple[str, tuple[str, ...]], Optional[str]] = {}

    @staticmethod
    def _normalize_term(value: str) -> str:
        """Normalize term for case-insensitive, punctuation-tolerant matching."""
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _resolve_response_to_term(
        self,
        response: str,
        available_terms: list[str],
    ) -> Optional[str]:
        """Resolve LLM response to the closest valid available term."""
        if not response:
            return None

        response_clean = response.strip().strip("\"'")
        if response_clean.upper() == "NONE":
            return None

        # Exact match first.
        if response_clean in available_terms:
            return response_clean

        # Case-insensitive exact match.
        response_lower = response_clean.lower()
        for term in available_terms:
            if term.lower() == response_lower:
                return term

        # Punctuation-insensitive normalized match.
        response_norm = self._normalize_term(response_clean)
        for term in available_terms:
            if self._normalize_term(term) == response_norm:
                return term

        # Substring fallback for verbose responses.
        for term in available_terms:
            term_lower = term.lower()
            if term_lower in response_lower or response_lower in term_lower:
                return term

        return None

    def _select_term_from_dictionary(
        self,
        variable_name: str,
        available_terms: list[str],
    ) -> Optional[str]:
        """Try deterministic keyword-based matching before calling LLM."""
        variable_key = variable_name.lower().strip()
        keyword_candidates = self._VARIABLE_TERM_KEYWORDS.get(variable_key, [])
        if not keyword_candidates:
            return None

        normalized_terms = {
            term: self._normalize_term(term)
            for term in available_terms
        }

        def _score(term: str, term_norm: str, keyword: str, keyword_norm: str, exact: bool) -> int:
            score = 0
            score += 100 if exact else 70

            if "total" in term.lower():
                score += 20
            if term.lower().startswith("total "):
                score += 10
            if "other" in term.lower() and "other" not in keyword.lower():
                score -= 15

            # Prefer closer-length normalized matches.
            score -= abs(len(term_norm) - len(keyword_norm)) // 5
            return score

        best_match: Optional[Tuple[str, int]] = None

        # Priority 1: exact normalized keyword match.
        for keyword in keyword_candidates:
            keyword_norm = self._normalize_term(keyword)
            for term, term_norm in normalized_terms.items():
                if term_norm == keyword_norm:
                    candidate_score = _score(term, term_norm, keyword, keyword_norm, exact=True)
                    if best_match is None or candidate_score > best_match[1]:
                        best_match = (term, candidate_score)

        if best_match is not None:
            return best_match[0]

        # Priority 2: substring normalized keyword match.
        for keyword in keyword_candidates:
            keyword_norm = self._normalize_term(keyword)
            for term, term_norm in normalized_terms.items():
                if keyword_norm and (keyword_norm in term_norm or term_norm in keyword_norm):
                    candidate_score = _score(term, term_norm, keyword, keyword_norm, exact=False)
                    if best_match is None or candidate_score > best_match[1]:
                        best_match = (term, candidate_score)

        if best_match is not None:
            return best_match[0]

        return None

    @staticmethod
    def safe_divide(
        numerator: Optional[float],
        denominator: Optional[float],
        default: Optional[float] = None,
    ) -> Optional[float]:
        """Safely divide two numbers."""
        if numerator is None or denominator is None:
            return default
        if denominator == 0:
            return default
        result = numerator / denominator
        if math.isnan(result) or math.isinf(result):
            return default
        return result

    def calculate_all_ratios(
        self,
        raw_extracted: Dict[str, Any],
        previous_period: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate ratios using LLM to match raw terms to formula variables.
        
        Parameters
        ----------
        raw_extracted : dict
            Raw extracted terms and values from balance sheet (no mapping to canonical names)
            
        Returns
        -------
        dict
            Nested dict: {category: {ratio_name: {value, formula, interpretation, llm_selection}}}
        """
        # Get list of available raw term names
        available_terms = sorted(raw_extracted.keys())
        term_summary = ", ".join(available_terms)
        
        logger.info(f"Available raw terms: {term_summary}")
        
        ratios = {
            "Key Financial Indicators": self._key_financial_indicators(
                raw_extracted,
                available_terms,
                previous_period,
            )
        }

        return ratios

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _find_direct_metric(
        self,
        data: Dict[str, Any],
        aliases: list[str],
    ) -> tuple[Optional[str], Optional[float]]:
        """Find direct KPI rows when the source already provides computed metrics."""
        alias_norms = [self._normalize_term(a) for a in aliases]
        for term, value in data.items():
            term_norm = self._normalize_term(str(term))
            if not any(alias in term_norm for alias in alias_norms):
                continue
            parsed = self._to_float(value)
            if parsed is not None:
                return str(term), parsed
        return None, None

    @staticmethod
    def _is_aggregate_term_liabilities_label(label: Optional[str]) -> bool:
        """Accept only aggregate liability labels, reject item-level loan lines."""
        if not label:
            return False
        text = label.lower()
        # Must look like a liabilities subtotal/aggregate row.
        if "liabilit" not in text:
            return False
        # Guard against picking a specific line item when subtotal exists.
        if "loan" in text and "liabilit" not in text:
            return False
        return True

    def _key_financial_indicators(
        self,
        data: Dict[str, Any],
        available_terms: list[str],
        previous_period: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ratios: Dict[str, Any] = {}

        # Reused balance-sheet anchors.
        ca_term = self._select_term_for_variable("Current Assets", available_terms, "Balance sheet liquidity")
        cl_term = self._select_term_for_variable("Current Liabilities", available_terms, "Balance sheet liquidity")

        direct_tnw_term, direct_tnw_value = self._find_direct_metric(
            data,
            ["tangible net worth", "net worth", "tnw"],
        )
        direct_tol_tnw_term, direct_tol_tnw_value = self._find_direct_metric(
            data,
            ["tol/tnw", "tol tnw", "toltnw"],
        )
        direct_nwc_term, direct_nwc_value = self._find_direct_metric(
            data,
            ["net working capital", "nwc"],
        )
        direct_cr_term, direct_cr_value = self._find_direct_metric(
            data,
            ["current ratio"],
        )
        direct_cash_accruals_term, direct_cash_accruals_value = self._find_direct_metric(
            data,
            ["cash accrual", "cash accruals"],
        )

        # 1) Net Sales Growth (%)
        net_sales_term = self._select_term_for_variable("Net Sales", available_terms, "Growth analysis")
        if net_sales_term and previous_period is not None:
            current_sales = self._to_float(data.get(net_sales_term))
            previous_sales = self._to_float(previous_period.get(net_sales_term))
            growth = self.safe_divide(
                (current_sales - previous_sales) if current_sales is not None and previous_sales is not None else None,
                previous_sales,
            )
            if growth is not None:
                growth_pct = growth * 100.0
                if growth_pct < 5:
                    interpretation = "Low/negative growth: demand slowdown risk"
                elif growth_pct > 40:
                    interpretation = "Very high growth: expansion may stress cash flows"
                elif 10 <= growth_pct <= 25:
                    interpretation = "Ideal range: healthy year-on-year growth"
                else:
                    interpretation = "Moderate growth"

                ratios["Net Sales Growth (%)"] = {
                    "value": growth_pct,
                    "percentage": growth_pct,
                    "formula": "((Net Sales current year - Net Sales previous year) / Net Sales previous year) * 100",
                    "interpretation": interpretation,
                    "llm_selection": f"{net_sales_term} (current) vs {net_sales_term} (previous)",
                }

        # 2) EBITDA Margin (%)
        ebitda_term = self._select_term_for_variable("EBITDA", available_terms, "Profitability")
        revenue_term = self._select_term_for_variable("Revenue", available_terms, "Profitability") or \
                       self._select_term_for_variable("Net Sales", available_terms, "Profitability")
        if ebitda_term and revenue_term:
            ebitda = self._to_float(data.get(ebitda_term))
            revenue = self._to_float(data.get(revenue_term))
            margin = self.safe_divide(ebitda, revenue)
            if margin is not None:
                margin_pct = margin * 100.0
                if margin_pct < 8:
                    interpretation = "Low margin: weak operating efficiency"
                elif margin_pct > 30:
                    interpretation = "Very high margin: may include temporary effects"
                elif 10 <= margin_pct <= 20:
                    interpretation = "Ideal range: strong operating profitability"
                else:
                    interpretation = "Moderate operating margin"

                ratios["EBITDA Margin (%)"] = {
                    "value": margin_pct,
                    "percentage": margin_pct,
                    "formula": "(EBITDA / Net Sales) * 100",
                    "interpretation": interpretation,
                    "llm_selection": f"{ebitda_term} / {revenue_term}",
                }

        # 3) Net Profit Margin (%)
        np_term = self._select_term_for_variable("Net Profit", available_terms, "Profitability")
        if np_term and revenue_term:
            net_profit = self._to_float(data.get(np_term))
            revenue = self._to_float(data.get(revenue_term))
            npm = self.safe_divide(net_profit, revenue)
            if npm is not None:
                npm_pct = npm * 100.0
                if npm_pct < 5:
                    interpretation = "Low margin: weaker bottom-line profitability"
                elif npm_pct > 20:
                    interpretation = "Very high margin: check non-recurring income"
                elif 5 <= npm_pct <= 15:
                    interpretation = "Ideal range: sustainable profitability"
                else:
                    interpretation = "Moderate profitability"

                ratios["Net Profit Margin (%)"] = {
                    "value": npm_pct,
                    "percentage": npm_pct,
                    "formula": "(Net Profit / Net Sales) * 100",
                    "interpretation": interpretation,
                    "llm_selection": f"{np_term} / {revenue_term}",
                }

        # 4) Cash Accruals
        depreciation_term = self._select_term_for_variable("Depreciation", available_terms)
        amortization_term = self._select_term_for_variable("Amortization", available_terms)
        net_profit = self._to_float(data.get(np_term)) if np_term else None
        depreciation = self._to_float(data.get(depreciation_term)) if depreciation_term else 0.0
        amortization = self._to_float(data.get(amortization_term)) if amortization_term else 0.0
        if direct_cash_accruals_value is not None:
            ratios["Cash Accruals"] = {
                "value": direct_cash_accruals_value,
                "formula": "Direct value from source",
                "interpretation": "Used directly from provided KPI row",
                "llm_selection": direct_cash_accruals_term,
            }
        elif net_profit is not None:
            cash_accruals = net_profit + (depreciation or 0.0) + (amortization or 0.0)
            if cash_accruals < 0:
                interpretation = "Negative: repayment difficulty risk"
            elif cash_accruals > 0:
                interpretation = "Positive: healthy internal cash generation"
            else:
                interpretation = "Neutral cash accruals"

            dep_label = depreciation_term if depreciation_term else "Depreciation"
            amo_label = amortization_term if amortization_term else "Amortization"
            ratios["Cash Accruals"] = {
                "value": cash_accruals,
                "formula": "Net Profit + Depreciation + Amortization",
                "interpretation": interpretation,
                "llm_selection": f"{np_term} + {dep_label} + {amo_label}",
            }

        # 5) Tangible Net Worth (TNW)
        equity_term = self._select_term_for_variable("Equity", available_terms)
        share_capital_term = self._select_term_for_variable("Share Capital", available_terms)
        reserves_term = self._select_term_for_variable("Reserves and Surplus", available_terms)

        tnw_value: Optional[float] = None
        tnw_selection: Optional[str] = None
        if equity_term:
            tnw_value = self._to_float(data.get(equity_term))
            tnw_selection = equity_term

        sc = self._to_float(data.get(share_capital_term)) if share_capital_term else None
        rs = self._to_float(data.get(reserves_term)) if reserves_term else None
        if sc is not None or rs is not None:
            composite_tnw = (sc or 0.0) + (rs or 0.0)
            # Prefer composite TNW when both components are present.
            if sc is not None and rs is not None:
                tnw_value = composite_tnw
                tnw_selection = (
                    f"{share_capital_term or 'Share Capital'} + "
                    f"{reserves_term or 'Reserves and Surplus'}"
                )
            elif tnw_value is None:
                tnw_value = composite_tnw
                tnw_selection = (
                    f"{share_capital_term or 'Share Capital'} + "
                    f"{reserves_term or 'Reserves and Surplus'}"
                )

        if direct_tnw_value is not None:
            tnw_value = direct_tnw_value
            tnw_selection = direct_tnw_term

        if tnw_value is not None:
            if tnw_value < 0:
                interpretation = "Negative net worth: weak financial base"
            elif tnw_value > 0:
                interpretation = "Positive net worth: stronger financial backing"
            else:
                interpretation = "Neutral net worth"

            ratios["Tangible Net Worth (TNW)"] = {
                "value": tnw_value,
                "formula": "Equity or (Share Capital + Reserves and Surplus)",
                "interpretation": interpretation,
                "llm_selection": tnw_selection,
            }

        # 6) TOL / TNW Ratio
        # TOL should exclude net worth. Preferred computation:
        #   TOL = Term Liabilities + Total Current Liabilities
        # Fallback:
        #   TOL = Total Liabilities - TNW
        # Last fallback:
        #   TOL = Total Liabilities (less accurate, but avoids empty output)
        total_liabilities_term = self._select_term_for_variable("Total Liabilities", available_terms)
        term_liabilities_term = self._select_term_for_variable("Term Liabilities", available_terms)

        tol_value: Optional[float] = None
        tol_selection: Optional[str] = None

        if term_liabilities_term and cl_term and self._is_aggregate_term_liabilities_label(term_liabilities_term):
            term_liabilities = self._to_float(data.get(term_liabilities_term))
            current_liabilities = self._to_float(data.get(cl_term))
            if term_liabilities is not None and current_liabilities is not None:
                tol_value = term_liabilities + current_liabilities
                tol_selection = f"{term_liabilities_term} + {cl_term}"

        if tol_value is None and total_liabilities_term and tnw_value is not None:
            total_liabilities = self._to_float(data.get(total_liabilities_term))
            if total_liabilities is not None:
                derived_tol = total_liabilities - tnw_value
                if derived_tol >= 0:
                    tol_value = derived_tol
                    tol_selection = f"{total_liabilities_term} - {tnw_selection}"

        if tol_value is None and total_liabilities_term:
            total_liabilities = self._to_float(data.get(total_liabilities_term))
            if total_liabilities is not None:
                tol_value = total_liabilities
                tol_selection = total_liabilities_term

        if direct_tol_tnw_value is not None:
            ratios["TOL / TNW Ratio"] = {
                "value": direct_tol_tnw_value,
                "formula": "Direct value from source",
                "interpretation": "Used directly from provided KPI row",
                "llm_selection": direct_tol_tnw_term,
            }
        elif tol_value is not None and tnw_value is not None:
            tol_tnw = self.safe_divide(tol_value, tnw_value)
            if tol_tnw is not None:
                if tol_tnw > 3:
                    interpretation = "High leverage: over-leveraged and risky"
                elif tol_tnw < 1:
                    interpretation = "Conservative leverage: low risk, possibly slower growth"
                elif tol_tnw <= 2:
                    interpretation = "Ideal range: balanced leverage"
                else:
                    interpretation = "Moderate leverage"

                ratios["TOL / TNW Ratio"] = {
                    "value": tol_tnw,
                    "formula": "Total Outside Liabilities / Tangible Net Worth",
                    "interpretation": interpretation,
                    "llm_selection": f"{tol_selection} / {tnw_selection}",
                }

        # 7) Net Working Capital (NWC)
        if direct_nwc_value is not None:
            ratios["Net Working Capital (NWC)"] = {
                "value": direct_nwc_value,
                "formula": "Direct value from source",
                "interpretation": "Used directly from provided KPI row",
                "llm_selection": direct_nwc_term,
            }

        if direct_cr_value is not None:
            ratios["Current Ratio"] = {
                "value": direct_cr_value,
                "formula": "Direct value from source",
                "interpretation": "Used directly from provided KPI row",
                "llm_selection": direct_cr_term,
            }

        if ca_term and cl_term:
            ca = self._to_float(data.get(ca_term))
            cl = self._to_float(data.get(cl_term))
            if ca is not None and cl is not None:
                if ratios.get("Net Working Capital (NWC)", {}).get("value") is None:
                    nwc = ca - cl
                    if nwc < 0:
                        interpretation = "Negative NWC: liquidity stress"
                    elif nwc > 0:
                        interpretation = "Positive NWC: smoother short-term operations"
                    else:
                        interpretation = "Neutral working capital"

                    ratios["Net Working Capital (NWC)"] = {
                        "value": nwc,
                        "formula": "Current Assets - Current Liabilities",
                        "interpretation": interpretation,
                        "llm_selection": f"{ca_term} - {cl_term}",
                    }

                # 8) Current Ratio
                if ratios.get("Current Ratio", {}).get("value") is None:
                    current_ratio = self.safe_divide(ca, cl)
                    if current_ratio is not None:
                        if current_ratio < 1:
                            interpretation = "Low (<1): short-term default risk"
                        elif current_ratio > 2.5:
                            interpretation = "High (>2.5): possible inefficient fund utilization"
                        elif 1.33 <= current_ratio <= 2:
                            interpretation = "Ideal range: good liquidity position"
                        else:
                            interpretation = "Moderate liquidity"

                        ratios["Current Ratio"] = {
                            "value": current_ratio,
                            "formula": "Current Assets / Current Liabilities",
                            "interpretation": interpretation,
                            "llm_selection": f"{ca_term} / {cl_term}",
                        }

        required_kpis = {
            "Net Sales Growth (%)": "((Net Sales current year - Net Sales previous year) / Net Sales previous year) * 100",
            "EBITDA Margin (%)": "(EBITDA / Net Sales) * 100",
            "Net Profit Margin (%)": "(Net Profit / Net Sales) * 100",
            "Cash Accruals": "Net Profit + Depreciation + Amortization",
            "Tangible Net Worth (TNW)": "Equity or (Share Capital + Reserves and Surplus)",
            "TOL / TNW Ratio": "Total Outside Liabilities / Tangible Net Worth",
            "Net Working Capital (NWC)": "Current Assets - Current Liabilities",
            "Current Ratio": "Current Assets / Current Liabilities",
        }

        for kpi_name, formula in required_kpis.items():
            if kpi_name not in ratios:
                ratios[kpi_name] = {
                    "value": None,
                    "formula": formula,
                    "interpretation": "Insufficient data in uploaded document for this indicator",
                    "llm_selection": None,
                }

        return ratios

    def _select_term_for_variable(
        self,
        variable_name: str,
        available_terms: list[str],
        context: str = ""
    ) -> Optional[str]:
        """
        Use LLM to select which raw term matches the formula variable.
        
        Returns the raw term name, or None if no match found.
        """
        cache_key = (variable_name.lower(), tuple(sorted(available_terms)))
        if cache_key in self._selection_cache:
            return self._selection_cache[cache_key]

        # 1) Dictionary/keyword matching first (deterministic).
        dictionary_match = self._select_term_from_dictionary(variable_name, available_terms)
        if dictionary_match:
            logger.info(
                "Dictionary selected '%s' for %s",
                dictionary_match,
                variable_name,
            )
            self._selection_cache[cache_key] = dictionary_match
            return dictionary_match

        # 2) Fallback to LLM only when dictionary matching fails.
        if not self.llm.enabled or not self.llm.client:
            logger.warning(f"LLM disabled; cannot select term for {variable_name}")
            self._selection_cache[cache_key] = None
            return None
            
        # Ask LLM which term matches this variable
        prompt = f"""From this list of balance sheet terms, which one represents '{variable_name}'?

Available terms: {', '.join(available_terms)}

{f'Context: {context}' if context else ''}

Return ONLY the exact term name from the list above, or 'NONE' if not found.
"""
        
        try:
            result = self.llm.client.chat.completions.create(
                model=self.llm.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=30,
                temperature=0.2,
            )
            response = result.choices[0].message.content.strip()

            resolved = self._resolve_response_to_term(response, available_terms)
            if resolved:
                logger.info(f"LLM selected '{resolved}' for {variable_name}")
                self._selection_cache[cache_key] = resolved
                return resolved

            logger.debug(
                "LLM response '%s' could not be resolved for %s",
                response,
                variable_name,
            )
            self._selection_cache[cache_key] = None
            return None
                
        except Exception as e:
            logger.error(f"LLM term selection failed for {variable_name}: {e}")
            self._selection_cache[cache_key] = None
            return None

