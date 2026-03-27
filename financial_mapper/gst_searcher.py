"""
GST Number Search and Details Extractor

Searches the official GST portal (https://services.gst.gov.in/services/searchtp)
and extracts company details using Selenium.
"""

import logging
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.webdriver import WebDriver
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    WebDriver = object  # Placeholder type hint

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

from financial_mapper.logging_setup import get_logger

logger = get_logger("gst_search")


@dataclass
class GSTDetails:
    """GST Company Details extracted from portal."""
    gstin: str
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    status: Optional[str] = None
    registration_date: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    business_type: Optional[str] = None
    principal_place: Optional[str] = None
    additional_places: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.additional_places is None:
            self.additional_places = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "gstin": self.gstin,
            "legal_name": self.legal_name,
            "trade_name": self.trade_name,
            "status": self.status,
            "registration_date": self.registration_date,
            "state": self.state,
            "district": self.district,
            "address": self.address,
            "business_type": self.business_type,
            "principal_place": self.principal_place,
            "additional_places": self.additional_places,
            "error": self.error,
        }


class GSTSearcher:
    """Search GST portal and extract details."""

    PORTAL_URL = "https://services.gst.gov.in/services/searchtp"
    TIMEOUT = 30

    def __init__(self, headless: bool = True, manual_captcha: bool = False):
        """
        Initialize GST Searcher.
        
        Parameters
        ----------
        headless : bool
            Run browser in headless mode (no UI)
        manual_captcha : bool
            If True, show browser window and wait for manual CAPTCHA entry.
            Overrides headless setting.
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium not installed. Run: pip install selenium")

        self.headless = headless
        self.manual_captcha = manual_captcha
        # Override headless if manual CAPTCHA mode
        if manual_captcha:
            self.headless = False
        self.driver = None

    def _init_driver(self):
        """Initialize and return Chrome WebDriver."""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_argument('--start-maximized')

        logger.info("Initializing Selenium WebDriver...")
        
        try:
            # Use webdriver-manager to automatically manage ChromeDriver
            if WEBDRIVER_MANAGER_AVAILABLE:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                logger.info("WebDriver initialized with webdriver-manager")
            else:
                # Fallback: system ChromeDriver
                driver = webdriver.Chrome(options=options)
                logger.info("WebDriver initialized with system ChromeDriver")
            
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def search(self, gstin: str, demo_mode: bool = False) -> GSTDetails:
        """
        Search GST portal for given GSTIN and extract details.
        
        Parameters
        ----------
        gstin : str
            15-character GSTIN to search
        demo_mode : bool
            If True, return demo data without hitting portal (for testing)
            
        Returns
        -------
        GSTDetails
            Extracted company details or error message
        """
        gstin = gstin.strip().upper()
        
        # Demo mode for testing without portal access
        if demo_mode:
            logger.info(f"[DEMO MODE] Returning sample data for: {gstin}")
            return GSTDetails(
                gstin=gstin,
                legal_name="Demo Company Limited",
                trade_name="Demo Trading Co",
                status="Active",
                registration_date="01/07/2017",
                state="Maharashtra",
                district="Mumbai",
                address="Demo Address, Mumbai, Maharashtra 400001",
                business_type="Retail",
                principal_place="Demo Address, Mumbai, Maharashtra 400001",
                error=None
            )
        
        logger.info(f"Searching GST portal for: {gstin}")

        try:
            self.driver = self._init_driver()
            
            # Navigate to portal
            logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)  # Let page load with JavaScript
            
            # The official portal has specific element IDs
            # Try to find the GSTIN input field using correct selector
            gstin_input = None
            
            # Try multiple strategies to find GSTIN input
            try:
                # Strategy 1: Look for input with placeholder text
                gstin_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Enter GSTIN') or contains(@placeholder, 'GSTIN')]"))
                )
                logger.info("✓ Found GSTIN input via placeholder XPath")
            except:
                try:
                    # Strategy 2: Look for any text input in the search form
                    gstin_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
                    )
                    logger.info("✓ Found GSTIN input via CSS selector")
                except:
                    try:
                        # Strategy 3: Look by name attribute
                        gstin_input = self.driver.find_element(By.NAME, "gstin")
                        logger.info("✓ Found GSTIN input via name attribute")
                    except:
                        pass

            if not gstin_input:
                # Get page source for debugging
                page_source = self.driver.page_source
                logger.error(f"Could not find GSTIN input. Page length: {len(page_source)} chars")
                return GSTDetails(
                    gstin=gstin, 
                    error="Portal structure changed. Could not find GSTIN input field."
                )

            # Clear and enter GSTIN
            gstin_input.clear()
            gstin_input.send_keys(gstin)
            logger.info(f"✓ Entered GSTIN: {gstin}")
            time.sleep(1)

            # Find and click search button
            search_button = None
            
            try:
                # Strategy 1: Button with text "SEARCH"
                search_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'SEARCH') or contains(text(), 'Search')]"))
                )
                logger.info("✓ Found search button via SEARCH text")
            except:
                try:
                    # Strategy 2: Button with type submit
                    search_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    logger.info("✓ Found search button via submit type")
                except:
                    try:
                        # Strategy 3: Any button near the input
                        search_button = self.driver.find_element(By.XPATH, "//button")
                        logger.info("✓ Found search button via first button")
                    except:
                        pass

            if not search_button:
                logger.error("Could not find search button")
                return GSTDetails(gstin=gstin, error="Could not find search button on portal")

            search_button.click()
            logger.info("✓ Search button clicked")
            time.sleep(2)
            
            # Try using JavaScript if click didn't work  
            try:
                self.driver.execute_script("arguments[0].click();", search_button)
                logger.info("✓ Form submitted via JavaScript")
            except:
                pass
            
            # If manual CAPTCHA mode, wait for user to complete it
            if self.manual_captcha:
                logger.info("\n" + "="*70)
                logger.info("MANUAL CAPTCHA MODE: Waiting for user input...")
                logger.info("="*70)
                logger.info("A browser window has opened showing the GST portal.")
                logger.info("You need to:")
                logger.info("  1. Wait for CAPTCHA image to appear")
                logger.info("  2. Enter the CAPTCHA characters in the input field")
                logger.info("  3. Click the SEARCH button")
                logger.info("  4. Allow time for results to load")
                logger.info("\nThe system will automatically extract results once they appear.")
                logger.info("="*70 + "\n")
                
                # Wait for user to complete and results to load (up to 5 minutes)
                try:
                    WebDriverWait(self.driver, 300).until(
                        lambda driver: len(driver.find_elements(By.TAG_NAME, "table")) > 0 or
                                       "no results" in driver.page_source.lower() or
                                       "not found" in driver.page_source.lower()
                    )
                    logger.info("✓ Search complete - results or error page detected")
                except:
                    logger.warning("⚠ Timeout waiting for results - may still be loading")
                    time.sleep(5)
            else:
                # Wait for results to load - multiple strategies
                time.sleep(3)
                
                # Wait for page to change or results to appear
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda driver: len(driver.find_elements(By.TAG_NAME, "table")) > 0 or 
                                       len(driver.find_elements(By.XPATH, "//*[contains(text(), 'records')]")) > 0 or
                                       len(driver.find_elements(By.XPATH, "//*[contains(@class, 'result')]")) > 0
                    )
                    logger.info("✓ Results page loaded")
                except:
                    logger.warning("⚠ Result elements not found, continuing anyway...")
                    time.sleep(3)

            # Extract details from results
            details = self._extract_details(gstin)
            return details

        except Exception as e:
            logger.error(f"Error searching GST portal: {e}", exc_info=True)
            return GSTDetails(gstin=gstin, error=f"Search failed: {str(e)}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("✓ WebDriver closed")
                except:
                    pass

    def _extract_details(self, gstin: str) -> GSTDetails:
        """Extract company details from search results."""
        details = GSTDetails(gstin=gstin)

        try:
            # Check for portal error messages first
            error_messages = []
            error_patterns = [
                "//div[contains(@class, 'error')]",
                "//div[contains(@class, 'alert')]",
                "//p[contains(text(), 'not found')]",
                "//p[contains(text(), 'invalid')]",
                "//span[contains(text(), 'No records')]",
                "//*[contains(text(), 'ERROR')]",
            ]
            
            for pattern in error_patterns:
                try:
                    elements = self.driver.find_elements(By.XPATH, pattern)
                    for elem in elements:
                        text = elem.text.strip()
                        if text and text.lower() not in ['', 'error']:
                            error_messages.append(text)
                            logger.warning(f"Portal error found: {text}")
                except:
                    pass
            
            if error_messages:
                error_text = " | ".join(error_messages[:2])  # First 2 errors
                details.error = f"Portal returned: {error_text}"
                logger.warning(f"Search had errors: {details.error}")
                return details

            # Look for results table/div
            results_found = False
            
            # Pattern 1: Look for table with results
            try:
                result_table = self.driver.find_element(By.XPATH, "//table[contains(@class, 'result') or contains(@class, 'data')]")
                results_found = True
                logger.info("✓ Found results table")
                
                # Extract from table rows
                rows = self.driver.find_elements(By.XPATH, ".//tr")
                for row in rows[:20]:  # Check first 20 rows
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            label = cells[0].text.strip().lower()
                            value = cells[1].text.strip()
                            
                            if not value or value.lower() in ['', 'n/a', 'na']:
                                continue
                            
                            if 'legal' in label and 'name' in label:
                                details.legal_name = value
                                logger.info(f"✓ Legal Name: {value[:40]}")
                            elif 'trade' in label and 'name' in label:
                                details.trade_name = value
                                logger.info(f"✓ Trade Name: {value[:40]}")
                            elif 'status' in label:
                                details.status = value
                                logger.info(f"✓ Status: {value}")
                            elif 'registration' in label or 'date' in label:
                                details.registration_date = value
                                logger.info(f"✓ Registration Date: {value}")
                            elif 'state' in label:
                                details.state = value
                                logger.info(f"✓ State: {value}")
                            elif 'address' in label:
                                details.address = value
                                logger.info(f"✓ Address: {value[:50]}")
                    except:
                        continue
            except:
                logger.debug("No results table found")

            # Pattern 2: Look for div/span based layout
            if not results_found:
                try:
                    # Look for key-value pairs in divs
                    info_divs = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'info') or contains(@class, 'field')]")
                    for div in info_divs[:20]:
                        try:
                            text = div.text.strip()
                            if ':' in text:
                                key, value = text.split(':', 1)
                                key = key.strip().lower()
                                value = value.strip()
                                
                                if 'legal' in key and 'name' in key:
                                    details.legal_name = value
                                    logger.info(f"✓ Legal Name (div): {value[:40]}")
                                    results_found = True
                        except:
                            continue
                except:
                    pass

            # If nothing extracted, check if portal returned valid HTML
            if not results_found:
                page_title = self.driver.title if self.driver else "Unknown"
                page_url = self.driver.current_url if self.driver else "Unknown"
                
                logger.warning(f"No results extracted. Page title: {page_title}, URL: {page_url}")
                
                # Check if we got redirected or got a valid response
                if 'search' in page_url.lower() or 'gst' in page_url.lower():
                    details.error = "Portal returned no results for this GSTIN. It may not be registered."
                else:
                    details.error = "Portal did not return expected results page."
            else:
                # We found some data
                if not any([details.legal_name, details.trade_name, details.status]):
                    details.error = "Partial data extracted - some fields missing"
                else:
                    logger.info(f"✓ Successfully extracted data for {gstin}")

        except Exception as e:
            logger.error(f"Error during extraction: {e}", exc_info=True)
            details.error = f"Extraction error: {str(e)}"

        return details


def search_gst_async(gstin: str, timeout: int = 60, manual_captcha: bool = False) -> GSTDetails:
    """
    Synchronous wrapper for GST search (for Flask routes).
    
    Parameters
    ----------
    gstin : str
        GSTIN to search
    timeout : int
        Maximum seconds to wait for search (ignored in manual mode)
    manual_captcha : bool
        If True, show browser and wait for manual CAPTCHA entry
        
    Returns
    -------
    GSTDetails
        Search results or error
    """
    try:
        searcher = GSTSearcher(headless=not manual_captcha, manual_captcha=manual_captcha)
        return searcher.search(gstin)
    except Exception as e:
        logger.error(f"GST search failed: {e}")
        return GSTDetails(gstin=gstin, error=f"Search failed: {str(e)}")
