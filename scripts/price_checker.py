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
    from parsers import get_parser  # noqa: E402

    session = _make_session()

    # ---------------------------------------------------------------------------
    # PASS 1: Fetch + extract prices for every product (no writes yet)
    # ---------------------------------------------------------------------------
    # fetched_prices: pid -> dict with raw_price + meta needed for decision
    fetched_prices: dict[str, dict] = {}
    # per_domain_prices: domain -> {price -> [pids]} for duplicate detection
    per_domain_prices: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    failed_skipped: list[tuple[str, str]] = []
    oos_pids: set[str] = set()

    logger.info("=== Pass 1: Fetching prices for all products ===")
    for product in data:
        pid = product.get("id", "?")
        url = product.get("product_url", "")

        if not url:
            logger.info("SKIP [%s]: no product_url", pid)
            failed_skipped.append((pid, "no product_url"))
            continue

        domain = urlparse(url).hostname or ""
        logger.info("Fetching [%s] %s", pid, url)

        html = fetch_html(session, url)
        if html is None:
            logger.warning("FAIL [%s]: fetch failed", pid)
            failed_skipped.append((pid, "fetch failed"))
            continue

        # Stock detection BEFORE price parse (OOS products handled even with no price)
        if _detect_stock_status(html) == "out_of_stock":
            oos_pids.add(pid)
            logger.info("  [%s] STOCK: out_of_stock detected", pid)
            continue

        # Extract price via Perplexity
        parser = get_parser(domain)
        is_tier2 = pid in TIER2_IDS

        # Build hint from product name + model number to help LLM locate main product
        product_name = product.get("product_name", "") or ""
        model = product.get("model", "") or ""
        product_hint = f"{product_name} {model}".strip()

        try:
            if is_tier2:
                raw_price = parser.extract_min_price(html, url, product_hint=product_hint)
            else:
                raw_price = parser.extract_price(html, url, product_hint=product_hint)
        except Exception as exc:
            logger.warning("PARSE ERROR [%s] %s: %s", pid, domain, exc)
            failed_skipped.append((pid, f"parse error: {exc}"))
            time.sleep(API_SLEEP)
            continue

        # Rate limiting — sleep after each API call
        time.sleep(API_SLEEP)

        price = _validate_price(raw_price)
        if price is None:
            logger.warning("SKIP [%s]: no valid price found (raw=%r)", pid, raw_price)
            failed_skipped.append((pid, f"no valid price (raw={raw_price!r})"))
            continue

        # Record for cross-product duplicate detection
        fetched_prices[pid] = {
            "price": price,
            "domain": domain,
            "is_tier2": is_tier2,
        }
        per_domain_prices[domain][price].append(pid)

    # ---------------------------------------------------------------------------
    # PASS 2: Detect cross-product duplicate prices (parser hallucination signal)
    # ---------------------------------------------------------------------------
    logger.info("=== Pass 2: Detecting duplicate-price clusters ===")
    duplicates = _detect_duplicate_prices(per_domain_prices)
    rejected_duplicate_pids: set[str] = set()
    rejected_duplicates: list[tuple[str, str, int]] = []  # (pid, domain, price)

    for (domain, price), pids in duplicates.items():
        logger.warning(
            "DUPLICATE CLUSTER: %s returned HK$%d for %d products (%s) — REJECTING ALL",
            domain, price, len(pids), ", ".join(pids),
        )
        for pid in pids:
            rejected_duplicate_pids.add(pid)
            rejected_duplicates.append((pid, domain, price))

    # ---------------------------------------------------------------------------
    # PASS 3: Apply updates (only for products surviving both safety checks)
    # ---------------------------------------------------------------------------
    logger.info("=== Pass 3: Applying updates ===")
    tier1_changed: list[str] = []
    tier2_changed: list[str] = []
    suspicious: list[tuple[str, int, int, float]] = []  # (pid, old, new, ratio)
    checked_count = 0

    for product in data:
        pid = product.get("id", "?")
        prev_stock = product.get("stock_status", "in_stock")

        # ---- Out-of-stock handling ----
        if pid in oos_pids:
            if prev_stock != "out_of_stock":
                product["stock_status"] = "out_of_stock"
                product["stock_status_changed"] = today
                logger.info("  [%s] STOCK: in_stock → out_of_stock", pid)
            else:
                product["stock_status"] = "out_of_stock"
            product["last_checked"] = today
            checked_count += 1
            continue

        # ---- Was this product successfully fetched + extracted? ----
        if pid not in fetched_prices:
            # Failed in Pass 1 — leave untouched
            continue

        # ---- LAYER 2 reject: parser returned duplicate price across domain ----
        if pid in rejected_duplicate_pids:
            # Do NOT update anything (not even last_checked) — we don't trust this fetch
            continue

        info = fetched_prices[pid]
        price = info["price"]
        is_tier2 = info["is_tier2"]

        current_min = product.get("price_min")
        try:
            current_min_int = int(float(current_min)) if current_min is not None else None
        except (TypeError, ValueError):
            current_min_int = None

        # ---- LAYER 1 reject: single-product sanity check ----
        if current_min_int is not None and current_min_int > 0 and price != current_min_int:
            if not _is_sane_change(current_min_int, price):
                ratio = price / current_min_int
                logger.warning(
                    "SUSPICIOUS [%s]: %d -> %d (ratio %.2fx), SKIPPING",
                    pid, current_min_int, price, ratio,
                )
                suspicious.append((pid, current_min_int, price, ratio))
                continue

        # ---- Stock status: in_stock confirmed ----
        stock_flipped_to_in = (prev_stock == "out_of_stock")
        if stock_flipped_to_in:
            product["stock_status"] = "in_stock"
            product["stock_status_changed"] = today
            logger.info("  [%s] STOCK: out_of_stock → in_stock (有貨了!)", pid)
        else:
            product["stock_status"] = "in_stock"

        force_price_update = stock_flipped_to_in
        checked_count += 1

        if current_min_int is not None and price == current_min_int and not force_price_update:
            # Price unchanged — only update last_checked
            product["last_checked"] = today
            logger.info("  [%s] unchanged at HK$%d — updated last_checked", pid, price)
        elif is_tier2:
            # Tier 2: only update price_min anchor + dates, NEVER touch price_max/price_display
            if current_min_int != price:
                logger.info(
                    "  [%s] TIER2 anchor: HK$%d → HK$%d (manual review needed)",
                    pid, current_min_int or 0, price,
                )
                product["price_min"] = price
                product["updated_date"] = today
                product["last_checked"] = today
                tier2_changed.append(pid)
            else:
                product["last_checked"] = today
        else:
            # Tier 1: update all price fields
            logger.info(
                "  [%s] TIER1 price: HK$%s → HK$%d",
                pid, current_min_int or "?", price,
            )
            product["price_min"] = price
            product["price_max"] = price
            product["price_display"] = f"HK${price:,}"
            product["updated_date"] = today
            product["last_checked"] = today
            tier1_changed.append(pid)

    # ---------------------------------------------------------------------------
    # Safety check — must not lose any products
    # ---------------------------------------------------------------------------
    assert len(data) == original_count, (
        f"SAFETY FAIL: product count changed! original={original_count} current={len(data)}"
    )
    if len(data) != original_count:
        logger.error(
            "SAFETY FAIL: product count changed! original=%d current=%d — ABORTING write.",
            original_count, len(data),
        )
        sys.exit(1)

    # Write back products.json
    PRODUCTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote %s (%d products)", PRODUCTS_JSON, len(data))

    # Rebuild standalone HTML
    rebuild_script = Path(__file__).resolve().parent / "rebuild_html.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("rebuild_html", rebuild_script)
    rebuild_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rebuild_mod)
    rebuild_mod.rebuild()

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print()
    print("=" * 60)
    print("Price Check Summary")
    print("=" * 60)
    print(f"Checked: {checked_count} products")
    print()
    print(f"Tier 1 changed ({len(tier1_changed)}) — auto-updated:")
    if tier1_changed:
        for pid in tier1_changed:
            print(f"  - {pid}")
    else:
        print("  (none)")
    print()
    print(f"Tier 2 anchor changed ({len(tier2_changed)}) — manual review needed:")
    if tier2_changed:
        for pid in tier2_changed:
            print(f"  - {pid}  *** manual review needed ***")
    else:
        print("  (none)")
    print()
    print(f"Failed/skipped ({len(failed_skipped)}):")
    if failed_skipped:
        for pid, reason in failed_skipped:
            print(f"  - {pid}: {reason}")
    else:
        print("  (none)")
    print()
    print(f"SUSPICIOUS — price change too large (>±25%), skipped for safety ({len(suspicious)}):")
    if suspicious:
        for pid, old_p, new_p, ratio in suspicious:
            print(f"  - {pid}: HK${old_p:,} → HK${new_p:,} ({ratio:.2f}x) *** manual review needed ***")
    else:
        print("  (none)")
    print()
    print(f"REJECTED — duplicate prices within same domain (parser hallucination, {len(rejected_duplicates)}):")
    if rejected_duplicates:
        for pid, domain, price in rejected_duplicates:
            print(f"  - {pid}: {domain} returned HK${price:,} (same as 3+ products on same site) *** SKIPPED ***")
    else:
        print("  (none)")
    print("=" * 60)


if __name__ == "__main__":
    main()
