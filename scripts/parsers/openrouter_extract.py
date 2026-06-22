"""
OpenRouter-based price extractor.
Replaces Perplexity (requires $5 prepay, no Alipay) and Gemini (HK geo-blocked).

Uses OpenRouter's OpenAI-compatible endpoint with FREE models.
Free tier: 20 RPM, 200 requests/day per model — fits 58 products/week easily.
"""
import os
import re
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Primary: Qwen3-Next 80B instruct (free, 262K context, strong instruction-following)
# Fallback: Llama 3.3 70B instruct (free, 131K context, stable)
# Updated 2026-06-22: old Gemini/DeepSeek free IDs returned 404 (model no longer hosted)
PRIMARY_MODEL = "qwen/qwen3-next-80b-a3b-instruct:free"
FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

_api_key = os.environ.get("OPENROUTER_API_KEY")

# Optional headers OpenRouter uses for analytics/ranking — not required
_REFERER = "https://github.com/ychoccu/ych-occu-rehab-aids-tracker"
_TITLE = "YCH Rehab Aids Tracker"


def _truncate_html(html: str, max_chars: int = 50000) -> str:
    """Strip <script>, <style>, comments. Keep main content."""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html)
    return html[:max_chars]


TIER1_PROMPT = """You are extracting the MAIN PRODUCT price from an e-commerce product page (Hong Kong retailer, prices in HK$).

The HTML content below is the COMPLETE source of truth. Do NOT use external knowledge. Use ONLY the HTML provided.

The page may contain:
- The main product's current price (what we want)
- The main product's original/list price (strikethrough, IGNORE this)
- Related products' prices (smaller, in sidebars or "you may also like" sections, IGNORE)
- Shipping/promo amounts e.g. "free shipping over $499" (IGNORE - this is a banner, not a price)

Return ONLY the main product's CURRENT SELLING PRICE as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify the main product price from the HTML, return exactly: UNKNOWN

Examples of valid responses: 2680
Examples of invalid responses: HK$2,680 / $2,680.00 / 2680.50 / "The price is 2680"

HTML content:
"""

TIER2_PROMPT = """You are extracting the LOWEST price from an e-commerce product page that sells multiple SIZE VARIANTS of the same product (Hong Kong retailer, prices in HK$).

The HTML content below is the COMPLETE source of truth. Do NOT use external knowledge. Use ONLY the HTML provided.

This product has multiple sizes/variants at different prices. We want the cheapest variant's current selling price.

IGNORE:
- Strikethrough/original prices (we want current selling prices)
- Related products' prices
- Shipping/promo amounts e.g. "free shipping over $499"

Return ONLY the LOWEST current variant price as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify variant prices, return exactly: UNKNOWN

HTML content:
"""


def _call_openrouter(prompt: str, model: str) -> Optional[str]:
    """Single OpenRouter API call. Returns response text or None."""
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 20,
    }
    headers = {
        "Authorization": f"Bearer {_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": _REFERER,
        "X-Title": _TITLE,
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # OpenRouter free models sometimes return empty choices on rate-limit/upstream issues
        if not data.get("choices"):
            err = data.get("error", {})
            logger.warning("OpenRouter empty choices (model=%s): %s", model, err)
            return None
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        logger.warning("OpenRouter API error (model=%s): %s", model, e)
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.warning("OpenRouter unexpected response (model=%s): %s", model, e)
        return None


def extract_price(html: str, url: str, tier: int = 1) -> Optional[int]:
    """
    Use OpenRouter to extract main product price (Tier 1) or lowest variant price (Tier 2).
    Tries PRIMARY_MODEL first, falls back to FALLBACK_MODEL if empty/error.
    Returns int or None.
    """
    if not _api_key:
        logger.error("OPENROUTER_API_KEY not set — cannot extract prices")
        return None

    clean_html = _truncate_html(html)
    if not clean_html.strip():
        return None

    prompt = (TIER2_PROMPT if tier == 2 else TIER1_PROMPT) + clean_html

    # Primary attempt
    text = _call_openrouter(prompt, PRIMARY_MODEL)

    # Fallback if primary failed
    if text is None:
        logger.info("Falling back to %s for %s", FALLBACK_MODEL, url)
        text = _call_openrouter(prompt, FALLBACK_MODEL)
        if text is None:
            return None

    if text.upper() == "UNKNOWN" or not text:
        return None

    # Parse integer
    m = re.search(r'\d+', text)
    if not m:
        logger.warning("OpenRouter returned non-numeric for %s: %r", url, text[:100])
        return None

    return int(m.group(0))
