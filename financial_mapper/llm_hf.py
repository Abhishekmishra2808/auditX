"""
Hugging Face LLM integration using OpenAI-compatible router endpoint.

Uses HuggingFace router (https://router.huggingface.co/v1/) with OpenAI Python client.
Provides LLM-driven field matching and semantic understanding for financial terms.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from financial_mapper.logging_setup import get_logger
from financial_mapper.schema import CANONICAL_NAMES

logger = get_logger("llm_hf")



@dataclass
class LLMMappingResult:
    """Result of an LLM mapping attempt."""

    concept: Optional[str]  # Canonical concept name if mapped
    confidence: float  # 0.0 to 1.0
    reason: str  # Explanation from the model
    raw_response: str  # Full raw JSON string for audit trail
    accepted: bool  # True if concept is in allowed list and confidence > threshold
    error: Optional[str] = None  # Error message if mapping failed

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging/storage."""
        return {
            "concept": self.concept,
            "confidence": self.confidence,
            "reason": self.reason,
            "raw_response": self.raw_response,
            "accepted": self.accepted,
            "error": self.error,
        }


class HuggingFaceMapper:
    """Wrapper around HuggingFace router endpoint using OpenAI client.

    Parameters
    ----------
    api_key : str
        HuggingFace API key (from environment or explicit)
    model_id : str
        Model identifier (e.g., "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai")
    confidence_threshold : float
        Minimum confidence (0.0-1.0) to accept a mapping
    timeout : int
        HTTP request timeout in seconds
    enabled : bool
        If False, all mapping calls return placeholder results
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai",
        confidence_threshold: float = 0.75,
        timeout: int = 20,
        enabled: bool = True,
    ) -> None:
        self.api_key = api_key or os.getenv("HF_API_KEY", "")
        self.model_id = model_id
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout
        self.enabled = enabled and bool(self.api_key)

        # Initialize OpenAI client pointing to HF router
        self.client: Optional[OpenAI] = None
        if self.enabled:
            try:
                self.client = OpenAI(
                    base_url="https://router.huggingface.co/v1/",
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
                logger.info(
                    "HuggingFaceMapper enabled: model=%s, endpoint=https://router.huggingface.co/v1/",
                    self.model_id,
                )
            except Exception as e:
                logger.error("Failed to initialize OpenAI client for HF router: %s", str(e))
                self.enabled = False
        
        if not self.enabled:
            logger.warning(
                "HuggingFaceMapper disabled: api_key=%s, enabled=%s",
                "not set" if not self.api_key else "***",
                enabled,
            )

    def map_term(
        self,
        raw_label: str,
        candidates: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> LLMMappingResult:
        """Map a raw financial label to a canonical concept via LLM.

        Parameters
        ----------
        raw_label : str
            The raw input label (e.g., "Curr. Liab.")
        candidates : list[str], optional
            Restrict mapping to one of these canonical names.
            If None, defaults to all CANONICAL_NAMES.
        context : dict, optional
            Extra context (section, nearby terms, etc.) to guide the LLM.

        Returns
        -------
        LLMMappingResult
            Contains mapped concept, confidence, acceptance flag, and audit trail.
        """
        if not self.enabled or not self.client:
            return LLMMappingResult(
                concept=None,
                confidence=0.0,
                reason="LLM mapping disabled",
                raw_response="",
                accepted=False,
                error="LLM disabled or no API key",
            )

        allowed = candidates or list(CANONICAL_NAMES)
        
        prompt = f"""You are a financial accounting expert. Given a raw financial field label, map it to the most appropriate canonical financial metric.

Raw label: "{raw_label}"
{f'Context: {context}' if context else ''}

Choose from these canonical concepts:
{', '.join(allowed)}

Respond in JSON format only:
{{
  "concept": "chosen_concept_or_null",
  "confidence": 0.0_to_1.0,
  "reason": "brief_explanation"
}}

If no mapping is appropriate, set concept to null."""

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3,
            )
            
            raw_response = response.choices[0].message.content.strip()
            logger.debug(f"LLM response: {raw_response}")
            
            # Parse JSON response
            parsed = json.loads(raw_response)
            concept = parsed.get("concept")
            confidence = float(parsed.get("confidence", 0.0))
            reason = parsed.get("reason", "")
            
            # Validate concept is in allowed list
            accepted = concept in allowed and confidence >= self.confidence_threshold
            
            return LLMMappingResult(
                concept=concept,
                confidence=confidence,
                reason=reason,
                raw_response=raw_response,
                accepted=accepted,
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM response was not valid JSON: {e}")
            return LLMMappingResult(
                concept=None,
                confidence=0.0,
                reason="Invalid response format",
                raw_response="",
                accepted=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"LLM mapping failed: {e}")
            return LLMMappingResult(
                concept=None,
                confidence=0.0,
                reason="LLM request failed",
                raw_response="",
                accepted=False,
                error=str(e),
            )

    def map_to_canonical(
        self,
        labels: list[str],
        candidates: Optional[list[str]] = None,
    ) -> dict[str, str]:
        """Map multiple financial labels to canonical fields in a single LLM call.

        This is the batch-optimised alternative to calling ``map_term()`` per
        label.  One API round-trip handles all labels at once.

        Parameters
        ----------
        labels:
            Raw financial term labels to map (e.g. ["Cash", "Trade Receivables"]).
        candidates:
            Restrict mapping to these canonical names.
            If None, defaults to all ``CANONICAL_NAMES``.

        Returns
        -------
        dict[str, str]
            ``{raw_label: canonical_name}`` for every label the LLM could map.
            Labels the LLM could not map are **omitted** from the dict.
        """
        if not self.enabled or not self.client or not labels:
            logger.warning("Batch mapping skipped — LLM disabled or no labels")
            return {}

        allowed = candidates or sorted(CANONICAL_NAMES)
        allowed_set = set(allowed)

        # Build a compact prompt
        label_list = "\n".join(f"  - {lbl}" for lbl in labels)
        canonical_list = ", ".join(allowed)

        prompt = f"""You are a financial accounting expert. Map each raw financial term below to its most appropriate canonical field name.

Raw terms:
{label_list}

Canonical fields (choose ONLY from this list):
{canonical_list}

Rules:
- Map each raw term to exactly one canonical field, or "null" if no match.
- Return a JSON object mapping raw term → canonical field.
- Do NOT invent new canonical fields.

Respond with ONLY a valid JSON object, nothing else. Example format:
{{"Cash and Cash Equivalents": "Cash and Cash Equivalents", "Sundry Debtors": "Trade Receivables"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=min(50 * len(labels), 2000),
                temperature=0.2,
            )

            raw_response = response.choices[0].message.content.strip()
            logger.debug("Batch LLM response: %s", raw_response)

            # Parse JSON — handle markdown code fences if present
            json_str = raw_response
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )

            parsed: dict[str, Any] = json.loads(json_str)

            # Validate: keep only entries where value is a valid canonical name
            result: dict[str, str] = {}
            for raw_label, canonical in parsed.items():
                if canonical in allowed_set:
                    result[raw_label] = canonical
                    logger.info("Batch mapped: %r → %r", raw_label, canonical)
                elif canonical and canonical != "null":
                    logger.warning(
                        "Batch LLM returned invalid canonical %r for %r — skipped",
                        canonical,
                        raw_label,
                    )

            logger.info(
                "Batch mapping complete: %d/%d labels mapped",
                len(result),
                len(labels),
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("Batch LLM response was not valid JSON: %s", e)
            return {}
        except Exception as e:
            logger.error("Batch LLM mapping failed: %s", e)
            return {}
