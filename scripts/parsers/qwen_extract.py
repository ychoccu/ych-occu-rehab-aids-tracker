"""
Qwen (Alibaba Model Studio) based price extractor.
Replaces previous attempts (all blocked in HK or rate-limited):
- Gemini -> HK geo-blocked
- Perplexity -> requires $5 credit-card prepay
- OpenRouter -> free tier only 50 req/day
- Groq -> HK geo-blocked (Forbidden)
- Cerebras -> HK geo-blocked (Cloudflare)

Qwen is HK-friendly (Alibaba is a Chinese company; has dedicated HK endpoint).
New accounts on Singapore endpoint get 1M tokens free per model, 90 days.
"""
import os
import re
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Primary: qwen-plus (balanced cost/quality, strong instruction-following)
# Fallback: qwen-turbo (cheapest, fastest)
# qwen-plus exhausted 2026-06-22. qwen-plus-latest = same quality, separate 1M quota.
# qwen-max too conservative (misses listed prices). Keep as fallback in case plus-latest exhausts.
PRIMARY_MODEL = "qwen-plus-latest"
FALLBACK_MODEL = "qwen-max"

# Singapore endpoint = International region with free quota
# Hong Kong endpoint exists too but no free quota
API_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

_api_key = os.environ.get("DASHSCOPE_API_KEY")


def _truncate_html(html: str, max_chars: int = 50000) -> str:
    """Strip <script>, <style>, comments. Keep main content."""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html)
    return html[:max_chars]


TIER1_PROMPT_TEMPLATE = """You are extracting the MAIN PRODUCT price from an e-commerce product page (Hong Kong retailer, prices in HK$).

{hint_section}The HTML content below is the COMPLETE source of truth. Do NOT use external knowledge. Use ONLY the HTML provided.

The page may contain:
- The main product's current price (what we want)
- The main product's original/list price (strikethrough or 原價, IGNORE this)
- Recently-viewed / related products / sidebar / nav menu products (with their OWN prices, IGNORE these — they are NOT the main product)
- Shipping/promo amounts e.g. "free shipping over $499" or 滿$1000免運費 (IGNORE - this is a banner, not a price)
- Empty cart amount HK$0 (IGNORE)

FOCUS: The MAIN PRODUCT's price usually appears NEAR its model number, name, or "加入購物車"/"Add to cart" button. It often appears as the LARGEST price on the page.

Return ONLY the main product's CURRENT SELLING PRICE as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify the main product price from the HTML, return exactly: UNKNOWN

Examples of valid responses: 2680
Examples of invalid responses: HK$2,680 / $2,680.00 / 2680.50 / "The price is 2680"

HTML content:
"""

TIER2_PROMPT_TEMPLATE = """You are extracting the LOWEST price from an e-commerce product page that sells multiple SIZE VARIANTS of the same product (Hong Kong retailer, prices in HK$).

{hint_section}The HTML content below is the COMPLETE source of truth. Do NOT use external knowledge. Use ONLY the HTML provided.

This product has multiple sizes/variants at different prices. We want the cheapest variant's current selling price.

IGNORE:
- Strikethrough/original prices (we want current selling prices)
- Recently-viewed / related products / sidebar / nav menu products with their own prices
- Shipping/promo amounts e.g. "free shipping over $499"
- Empty cart amount HK$0

Return ONLY the LOWEST current variant price as a single integer (no currency symbol, no commas, no decimals).
If you cannot reliably identify variant prices, return exactly: UNKNOWN

HTML content:
"""


def _call_qwen(prompt: str, model: str) -> Optional[str]:
    """Single Qwen API call via OpenAI-compatible endpoint. Returns response text or None."""
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
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("choices"):
            logger.warning("Qwen empty choices (model=%s): %s", model, data.get("error", {}))
            return None
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        logger.warning("Qwen API error (model=%s): %s", model, e)
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.warning("Qwen unexpected response (model=%s): %s", model, e)
        return None


def extract_price(html: str, url: str, tier: int = 1, product_hint: str = "") -> Optional[int]:
    """
    Use Qwen to extract main product price (Tier 1) or lowest variant price (Tier 2).
    Tries PRIMARY_MODEL first, falls back to FALLBACK_MODEL if empty/error.
    `product_hint` is the product name / model number to help locate the main product
    among navigation/sidebar noise (e.g. "取物器 FHA-HE-1626").
    Returns int or None.
    """
    if not _api_key:
        logger.error("DASHSCOPE_API_KEY not set — cannot extract prices")
        return None

    clean_html = _truncate_html(html)
    if not clean_html.strip():
        return None

    hint_section = ""
    if product_hint:
        hint_section = (
            f"MAIN PRODUCT identifier (use this to locate the right price; "
            f"DO NOT pick prices of other products near it): {product_hint}\n\n"
        )

    template = TIER2_PROMPT_TEMPLATE if tier == 2 else TIER1_PROMPT_TEMPLATE
    prompt = template.format(hint_section=hint_section) + clean_html

    text = _call_qwen(prompt, PRIMARY_MODEL)

    if text is None:
        logger.info("Falling back to %s for %s", FALLBACK_MODEL, url)
        text = _call_qwen(prompt, FALLBACK_MODEL)
        if text is None:
            return None

    if text.upper() == "UNKNOWN" or not text:
        return None

    m = re.search(r'\d+', text)
    if not m:
        logger.warning("Qwen returned non-numeric for %s: %r", url, text[:100])
        return None

    return int(m.group(0))
