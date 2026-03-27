"""
GSTIN (Goods and Services Tax Identification Number) validation and utilities.

GSTIN format (India):
- 15 alphanumeric characters
- Structure: AABBU9999AZZZ0
  - AA: State code (2 digits)
  - BB: PAN (first 5 chars of PAN)
  - U: Entity type
  - 9999: Serial number (4 digits)
  - A: First char of PAN first name
  - ZZZ: Business division (3 chars)
  - 0: Checksum (1 char)

Ref: https://services.gst.gov.in/services/searchtp
"""

import re
from typing import Tuple


def validate_gstin(gstin: str, strict: bool = False) -> Tuple[bool, str]:
    """
    Validate GSTIN format.
    
    Parameters
    ----------
    gstin : str
        The GSTIN number to validate
    strict : bool
        If True, enforce strict GSTIN format rules
        If False (default), allow any 15-char alphanumeric (let portal validate)
        
    Returns
    -------
    Tuple[bool, str]
        (is_valid, message)
    """
    if not gstin:
        return False, "GSTIN cannot be empty"
    
    gstin = gstin.strip().upper()
    
    # Check length (only hard requirement)
    if len(gstin) != 15:
        return False, "GSTIN must be 15 characters long"
    
    # Check format: alphanumeric only (only hard requirement)
    if not re.match(r'^[A-Z0-9]{15}$', gstin):
        return False, "GSTIN must contain only letters (A-Z) and numbers (0-9)"
    
    # If strict mode, enforce detailed format rules
    if strict:
        # Validate state code (first 2 digits) - check if it's numeric and valid
        state_code = gstin[:2]
        if not state_code.isdigit():
            return False, "First 2 characters must be numeric (state code)"
        
        state_code_int = int(state_code)
        # Valid state codes in India: 01-36
        if state_code_int < 1 or state_code_int > 36:
            return False, f"Invalid state code: {state_code}. Must be between 01 and 36"
        
        # Position 8 should be entity type (usually 1, 2, or 3)
        entity_type = gstin[7]
        if not entity_type.isdigit():
            return False, "Position 8 (entity type) must be numeric"
        
        # Positions 9-12 should be numeric (serial number)
        serial = gstin[8:12]
        if not serial.isdigit():
            return False, "Positions 9-12 must be numeric (serial number)"
    
    return True, "Valid GSTIN format"


def get_gst_portal_url(gstin: str) -> str:
    """
    Get the GST portal search URL for the given GSTIN.
    
    Parameters
    ----------
    gstin : str
        The GSTIN number (validated format)
        
    Returns
    -------
    str
        URL to search the GSTIN on official GST portal
    """
    gstin_clean = gstin.strip().upper()
    # Official GST search portal
    base_url = "https://services.gst.gov.in/services/searchtp"
    return f"{base_url}?gstin={gstin_clean}"


def format_gstin_display(gstin: str) -> str:
    """Format GSTIN for nice display (XX-XXXXX-XXXX-XXZ)."""
    gstin = gstin.strip().upper()
    if len(gstin) != 15:
        return gstin
    return f"{gstin[:2]}-{gstin[2:7]}-{gstin[7:12]}-{gstin[12:]}"
