"""
Gemini-based price extractor. Replaces all per-domain regex parsers.
"""
import os
import re
import logging
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Use free tier model: 15 RPM, 1,500 RPD
MODEL = "gemini-2.5-flash"

_api_key = os.environ.get("GEMINI_API_KEY")
if _api_key:
    genai.configure(api_key=_api_key)
    _model = genai.GenerativeModel(MODEL)
else:
    _model = None


def _truncate_html(html: str, max_chars: int = 50000) -> str:
    """
    Strip <script>, <style>, comments. Keep main content.
    Gemini Flash has 1M token context but we limit for speed/cost.
    """
    # Remove scripts, styles, comments
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html)
    return html[:max_chars]


TIER1_PROMPT = """You are extracting the MAIN PRODUCT price from an e-commerce product page (Hong Kong retailer, prices in HK$).

The page may contain:
- The main product's current price (what we want)
- The main product's original/list price (strikethrough, IGNORE this)
- Related products' prices (smaller, in sidebars or "you may also like" sections, IGNORE)
- Shipping/promo amounts (IGNORE)

Return ONLY the main product's CURRENT SELLING PRICE as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify the main product price, return exactly: UNKNOWN

Examples of valid responses: 2680
Examples of invalid responses: HK$2,680 / $2,680.00 / 2680.50 / "The price is 2680"

HTML content:
"""

TIER2_PROMPT = """You are extracting the LOWEST price from an e-commerce product page that sells multiple SIZE VARIANTS of the same product (Hong Kong retailer, prices in HK$).

This product has multiple sizes/variants at different prices. We want the cheapest variant's current selling price.

IGNORE:
- Strikethrough/original prices (we want current selling prices)
- Related products' prices
- Shipping/promo amounts

Return ONLY the LOWEST current variant price as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify variant prices, return exactly: UNKNOWN

HTML content:
"""


def extract_price(html: str, url: str, tier: int = 1) -> Optional[int]:
    """
    Use Gemini to extract main product price (Tier 1) or lowest variant price (Tier 2).
    Returns int or None.
    """
    if _model is None:
        logger.error("GEMINI_API_KEY not set — cannot extract prices")
        return None

    clean_html = _truncate_html(html)
    if not clean_html.strip():
        return None

    prompt = (TIER2_PROMPT if tier == 2 else TIER1_PROMPT) + clean_html

    try:
        resp = _model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": 20,
            }
        )
        text = resp.text.strip()
    except Exception as e:
        logger.warning("Gemini API error for %s: %s", url, e)
        return None

    if text.upper() == "UNKNOWN" or not text:
        return None

    # Parse integer
    m = re.search(r'\d+', text)
    if not m:
        logger.warning("Gemini returned non-numeric for %s: %r", url, text[:100])
        return None

    return int(m.group(0))
