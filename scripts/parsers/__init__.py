"""
Per-supplier CSS-selector parsers, with AI fallback.

Strategy: For each supplier we know, use hardcoded CSS selectors (fast, ~98% reliable).
If the CSS parse returns nothing OR the supplier is unknown, fall back to the AI extractor.

History:
- Originally Gemini -> blocked in Hong Kong (2026-06)
- Perplexity -> requires $5 prepay credit card (no Alipay)
- OpenRouter -> free tier only 50 req/day
- Groq -> blocked in Hong Kong (Forbidden)
- Cerebras -> blocked in Hong Kong (Cloudflare)
- Qwen (Alibaba) -> HK-friendly, 1M tokens/model free 90 days
- DeepSeek (中國) -> HK-friendly, cheap, used for AI fallback now
- 2026-06-30: Added per-supplier CSS parsers for ~98% reliable extraction;
  AI is now only fallback for unknown suppliers or when CSS parse fails.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .qwen_extract import extract_price as _ai_extract

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRICE_NUMBER_RE = re.compile(r"[\d,]+\.?\d*")


def _parse_price_text(text: str) -> Optional[int]:
    """Extract first sensible HK$ price number from a text string.

    Returns int (rounded), or None if no plausible number found.
    Filters out 0 (unset price) and absurdly small/large values.
    """
    if not text:
        return None
    # Remove HK$, HKD, $, commas, whitespace
    cleaned = text.replace(",", "")
    matches = _PRICE_NUMBER_RE.findall(cleaned)
    for m in matches:
        try:
            val = float(m)
        except ValueError:
            continue
        if val <= 0 or val > 1_000_000:
            continue
        # Filter obvious garbage (e.g. percentage "20")
        if val < 10:
            continue
        return int(round(val))
    return None


def _domain_key(domain: str) -> str:
    """Normalize domain by stripping www. and lowercasing."""
    if not domain:
        return ""
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    return d


# ---------------------------------------------------------------------------
# Per-supplier CSS extractors
# ---------------------------------------------------------------------------


def _extract_healthyliving(soup) -> Optional[int]:
    """healthyliving.com.hk uses meta tag + JSON-LD (Shopify-like)."""
    # Most reliable: meta product:price:amount
    meta = soup.find("meta", attrs={"property": "product:price:amount"})
    if meta and meta.get("content"):
        return _parse_price_text(meta["content"])
    # Fallback: JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.string or ""
        m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', txt)
        if m:
            return _parse_price_text(m.group(1))
    return None


def _extract_justmed(soup) -> Optional[int]:
    """justmed.com.hk: First .product-price on detail page is main product price."""
    el = soup.select_one(".product-price")
    if el:
        return _parse_price_text(el.get_text(strip=True))
    return None


def _extract_gethealth(soup) -> Optional[int]:
    """gethealth.com.hk: WooCommerce-like. meta[itemprop=price] is most reliable.

    Returns the lower-bound when price is a range (e.g. "$2,900-$3,200").
    """
    meta = soup.find("meta", attrs={"itemprop": "price"})
    if meta and meta.get("content"):
        return _parse_price_text(meta["content"])
    # Fallback: .entry-summary .price (main product summary block)
    el = soup.select_one(".entry-summary .price, .summary .price")
    if el:
        return _parse_price_text(el.get_text(strip=True))
    return None


def _extract_healthtop(soup) -> Optional[int]:
    """healthtop.com.hk (OpenCart): .price-new is current sale price.

    NOTE: OpenCart uses confusing IDs - #price-old actually has class .price-new for
    "current price". We use class selector to be safe.
    """
    # Try .price-new (current price), even if id might be misleading
    el = soup.select_one(".price-new")
    if el:
        return _parse_price_text(el.get_text(strip=True))
    # Fallback: itemprop=price
    el = soup.find(attrs={"itemprop": "price"})
    if el:
        return _parse_price_text(el.get_text(strip=True))
    return None


def _extract_medicare(soup) -> Optional[int]:
    """medicare.com.hk has two product layouts:
    - Standard: .list-row.current h3.price
    - Compact:  .item-cart .price (div, not h3)
    Try in order; either gives the current product's price.
    """
    selectors = [
        ".list-row.current h3.price",
        ".item-cart .price",
        "h3.price",
        ".price",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            price = _parse_price_text(el.get_text(strip=True))
            if price is not None:
                return price
    return None


def _extract_easy66(soup) -> Optional[int]:
    """easy66.com.hk (Shoplazza-like): .price-sale takes priority over .price-regular."""
    # Prefer .price-sale (discount price). If only .price-regular, use that.
    el = soup.select_one(".price-sale.price.js-price")
    if not el:
        el = soup.select_one(".price-sale")
    if el:
        price = _parse_price_text(el.get_text(strip=True))
        if price:
            return price
    el = soup.select_one(".price-regular.price.js-price")
    if not el:
        el = soup.select_one(".price-regular .price")
    if el:
        return _parse_price_text(el.get_text(strip=True))
    return None


def _extract_nrmedic(soup) -> Optional[int]:
    """nrmedic.com (OpenCart-like): .price-new on product page."""
    el = soup.select_one(".price-section .price-new")
    if not el:
        el = soup.select_one(".price-new")
    if el:
        return _parse_price_text(el.get_text(strip=True))
    return None


def _extract_rehabexpress(soup) -> Optional[int]:
    """rehabexpress.com.hk (Magento): [data-price-amount] on main product."""
    # Magento marks main product price with data-price-type="finalPrice"
    el = soup.select_one(
        '.product-info-price [data-price-amount], '
        '.product-info-main [data-price-amount]'
    )
    if el and el.get("data-price-amount"):
        return _parse_price_text(el["data-price-amount"])
    # Fallback: first [data-price-amount] not equal to 0
    for el in soup.select("[data-price-amount]"):
        amt = el.get("data-price-amount", "")
        price = _parse_price_text(amt)
        if price:
            return price
    return None


def _extract_aidapt(soup) -> Optional[int]:
    """aidapt.com.hk (Shopify): meta tag or JSON-LD.

    NOTE: w bb3 uses /search URL which has multiple products, so this rarely
    has a single main-product price. Fall back to AI.
    """
    meta = soup.find("meta", attrs={"property": "product:price:amount"})
    if meta and meta.get("content"):
        return _parse_price_text(meta["content"])
    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.string or ""
        m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', txt)
        if m:
            return _parse_price_text(m.group(1))
    return None


# Suppliers that do NOT list prices online (always require contact).
# For these, we skip CSS parsing and let the AI return UNKNOWN, which causes
# the product to be marked as needing manual price reference.
_NO_PRICE_SUPPLIERS = {
    "justicemed.com",
    "suprememed.com.hk",
}


_EXTRACTORS = {
    "healthyliving.com.hk": _extract_healthyliving,
    "justmed.com.hk": _extract_justmed,
    "gethealth.com.hk": _extract_gethealth,
    "healthtop.com.hk": _extract_healthtop,
    "medicare.com.hk": _extract_medicare,
    "easy66.com.hk": _extract_easy66,
    "nrmedic.com": _extract_nrmedic,
    "rehabexpress.com.hk": _extract_rehabexpress,
    "aidapt.com.hk": _extract_aidapt,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_parser(domain: str):
    """Return parser for the given domain. CSS first, AI fallback."""
    key = _domain_key(domain)
    return _SupplierParser(key)


class _SupplierParser:
    """CSS parse first; on failure fall back to AI extractor."""

    def __init__(self, domain_key: str):
        self.domain = domain_key
        self.extractor = _EXTRACTORS.get(domain_key)
        self.skip_css = domain_key in _NO_PRICE_SUPPLIERS

    def _try_css(self, html: str) -> Optional[int]:
        if self.skip_css or not self.extractor or not BeautifulSoup or not html:
            return None
        try:
            soup = BeautifulSoup(html, "html.parser")
            price = self.extractor(soup)
            if price is not None:
                logger.info("  CSS parse [%s] -> %d", self.domain, price)
            return price
        except Exception as exc:
            logger.warning("  CSS parser error [%s]: %s", self.domain, exc)
            return None

    def extract_price(self, html: str, url: str, product_hint: str = "") -> Optional[int]:
        price = self._try_css(html)
        if price is not None:
            return price
        # AI fallback
        if self.extractor:
            logger.info("  CSS parse [%s] failed, falling back to AI", self.domain)
        return _ai_extract(html, url, tier=1, product_hint=product_hint)

    def extract_min_price(self, html: str, url: str, product_hint: str = "") -> Optional[int]:
        # Tier 2 (price ranges): CSS already returns the lower bound for ranges
        # (we parse the first number found). Use same flow.
        price = self._try_css(html)
        if price is not None:
            return price
        if self.extractor:
            logger.info("  CSS parse [%s] failed (tier2), falling back to AI", self.domain)
        return _ai_extract(html, url, tier=2, product_hint=product_hint)
