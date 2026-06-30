#!/usr/bin/env python3
"""
YCH Rehab Aids Tracker — Weekly Price Checker
Runs Saturday 9am HKT via GitHub Actions.

Architecture (3-pass for safety):
  Pass 1: Fetch HTML + extract raw price for every product (no writes).
  Pass 2: Cross-product duplicate detection — reject any (domain, price)
          returned for 3+ products on the same supplier domain.
  Pass 3: Apply updates only to products surviving both safety checks
          (sane single-product change + not flagged as duplicate).

Safety rules:
  - NEVER delete any product.
  - Only modify: price_min, price_max, price_display, last_checked, updated_date,
    stock_status, stock_status_changed.
  - Tier 2 products: NEVER touch price_max or price_display.
  - assert len(data) == original_count before writing.
"""

import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
PRODUCTS_JSON = REPO / "products.json"

# ---------------------------------------------------------------------------
# Tier 2 product IDs (range-priced): only update price_min anchor
# ---------------------------------------------------------------------------
TIER2_IDS = {"tr1", "tr2", "tr3", "tr4", "tr5", "hr1", "hr2", "hr3", "hr4", "hr5", "hr6"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting — Perplexity Sonar tier 0/1 = 20 RPM
# Sleep after each API call to stay well within limits.
# ---------------------------------------------------------------------------
API_SLEEP = 2.5  # seconds between products (~24 RPM, under Groq 30 RPM limit)

# ---------------------------------------------------------------------------
# HTTP session with retry logic
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 20  # seconds


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


# ---------------------------------------------------------------------------
# Stock detection keywords
# ---------------------------------------------------------------------------
# IMPORTANT: Keep keywords SPECIFIC. Short fragments like "售完" or "缺貨"
# alone will false-trigger on:
#   - SHOPLINE templates: "售完 商品存貨不足，未能加入購物車" (generic cart UI on every page)
#   - Promo copy: "優惠期至... 送完即止" (substring match on 「售完」)
#   - Category/home pages: stock label of a SIBLING product (e.g. rehabexpress home page)
# So we use full-phrase keywords only.
OUT_OF_STOCK_KEYWORDS = [
    "未有庫存",
    "暫無庫存",
    "暂無庫存",
    "商品已售完",
    "此商品已售完",
    "本商品已售完",
    "已售罄",
    "售罄",
    "out of stock",
    "sold out",
    "currently unavailable",
]


def _detect_stock_status(html: str) -> str | None:
    """Return 'out_of_stock' if any OOS keyword found in VISIBLE text, else None.

    IMPORTANT: Strips <script> and <style> blocks before searching, because some
    sites (e.g. justmed.com.hk) embed JS inventory logic like
    `$('#stockText').text('Sold out')` which would otherwise trigger a false positive.
    """
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style/noscript blocks — they're not visible text
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        haystack = soup.get_text(separator=" ", strip=True).lower()
    except Exception:
        # Fallback: regex-strip script/style if BeautifulSoup unavailable
        import re
        cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        haystack = cleaned.lower()
    for kw in OUT_OF_STOCK_KEYWORDS:
        if kw.lower() in haystack:
            return "out_of_stock"
    return None


# ---------------------------------------------------------------------------
# Price validation
# ---------------------------------------------------------------------------
PRICE_MIN_VALID = 20
PRICE_MAX_VALID = 100_000


def _validate_price(price) -> int | None:
    """Return price as int if within valid range, else None."""
    if price is None:
        return None
    try:
        v = int(price)
    except (TypeError, ValueError):
        return None
    return v if PRICE_MIN_VALID <= v <= PRICE_MAX_VALID else None


# ---------------------------------------------------------------------------
# LAYER 1: Per-product sanity check — reject implausible price changes
# ---------------------------------------------------------------------------
# Tightened 2026-06-22 after parser hallucinated wrong prices for 33 products
# Old threshold (0.33x-3.0x) was too loose: e.g. $2,400→$1,980 (0.825x) passed
# even though it was wrong. New threshold: ±25% (0.75x-1.33x).
# Real supplier price changes within a week rarely exceed ±25%.
def _is_sane_change(old_price: int, new_price: int) -> bool:
    """Reject changes where new price is < 75% or > 133% of old price (likely parser error)."""
    if old_price <= 0:
        return True  # No previous price to compare
    ratio = new_price / old_price
    return 0.75 <= ratio <= 1.33


# ---------------------------------------------------------------------------
# LAYER 2: Cross-product duplicate detection
# ---------------------------------------------------------------------------
# If the parser returns the SAME exact price for 3+ different products on the
# SAME supplier domain, that's a strong sign the parser is hallucinating (e.g.
# picking up a shipping cost or a banner price). Reject all of them.
# This was the root cause of the 2026-06-21 incident:
#   healthyliving: 3 products all = HK$499 (the "free shipping over $499" banner)
#   justmed: 7 products all = HK$1,980
#   gethealth: 5 products all = HK$800
#   healthtop: 3 products all = HK$1,000
def _detect_duplicate_prices(per_domain_prices: dict) -> dict:
    """Return {(domain, price): [pids]} for prices that repeat 3+ times within a domain.
    These will be skipped to prevent mass-overwrite from a hallucinating parser.
    """
    duplicates = {}
    for domain, price_to_pids in per_domain_prices.items():
        for price, pids in price_to_pids.items():
            if len(pids) >= 3:
                duplicates[(domain, price)] = pids
    return duplicates


# ---------------------------------------------------------------------------
# Fetch HTML
# ---------------------------------------------------------------------------
def fetch_html(session: requests.Session, url: str) -> str | None:
    """Fetch a product URL and return HTML string or None on failure.
    Falls back to verify=False if SSL verification fails (some suppliers have
    broken cert chains but otherwise serve normally).
    """
    from js_fetch import needs_js_render, fetch_html_with_browser
    if needs_js_render(url):
        return fetch_html_with_browser(url)

    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.exceptions.SSLError as exc:
        # Retry without SSL verification (cert chain issue on supplier side)
        logger.warning("SSL FAIL [%s]: %s — retrying with verify=False", url, exc)
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True, verify=False)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc2:
            logger.warning("FETCH FAIL (after SSL fallback) [%s]: %s", url, exc2)
            return None
    except requests.RequestException as exc:
        logger.warning("FETCH FAIL [%s]: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Today's date (HKT = UTC+8)
# ---------------------------------------------------------------------------
def _today_hkt() -> str:
    hkt = timezone(timedelta(hours=8))
    return datetime.now(timezone.utc).astimezone(hkt).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    today = _today_hkt()
    logger.info("=== YCH Price Checker starting — date: %s ===", today)

    # Load products.json
    raw = PRODUCTS_JSON.read_text(encoding="utf-8")
    data: list[dict] = json.loads(raw)
    original_count = len(data)
    logger.info("Loaded %d products from %s", original_count, PRODUCTS_JSON)

    # Import parser dispatch table
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from parsers import
