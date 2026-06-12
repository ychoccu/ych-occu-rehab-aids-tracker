#!/usr/bin/env python3
"""
YCH Rehab Aids Tracker — Weekly Price Checker
Backup for Perplexity AI cron (runs Saturday 9am HKT via GitHub Actions).

Safety rules:
  - NEVER delete any product.
  - Only modify: price_min, price_max, price_display, last_checked, updated_date
  - Tier 2 products: NEVER touch price_max or price_display.
  - assert len(data) == original_count before writing.
"""

import json
import logging
import sys
import time
from datetime import date, datetime, timezone, timedelta
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
# Rate limiting — Gemini free tier: 15 RPM
# Sleep after each Gemini call to stay well within the limit.
# ---------------------------------------------------------------------------
GEMINI_SLEEP = 5.0  # seconds between products

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
# Sanity check — reject implausible price changes
# ---------------------------------------------------------------------------
def _is_sane_change(old_price: int, new_price: int) -> bool:
    """Reject changes where new price is < 1/3 or > 3x old price (likely parser error)."""
    if old_price <= 0:
        return True  # No previous price to compare
    ratio = new_price / old_price
    return 0.33 <= ratio <= 3.0


# ---------------------------------------------------------------------------
# Fetch HTML
# ---------------------------------------------------------------------------
def fetch_html(session: requests.Session, url: str) -> str | None:
    """Fetch a product URL and return HTML string or None on failure."""
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
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
    # Adjust sys.path so relative imports work when run directly
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from parsers import get_parser  # noqa: E402

    session = _make_session()

    tier1_changed: list[str] = []
    tier2_changed: list[str] = []
    failed_skipped: list[tuple[str, str]] = []
    suspicious: list[tuple[str, int, int, float]] = []  # (pid, old, new, ratio)
    checked_count = 0

    for product in data:
        pid = product.get("id", "?")
        url = product.get("product_url", "")

        if not url:
            logger.info("SKIP [%s]: no product_url", pid)
            failed_skipped.append((pid, "no product_url"))
            continue

        domain = urlparse(url).hostname or ""
        logger.info("Checking [%s] %s", pid, url)

        # Fetch HTML
        html = fetch_html(session, url)
        if html is None:
            logger.warning("FAIL [%s]: fetch failed", pid)
            failed_skipped.append((pid, "fetch failed"))
            continue

        # Get parser (unified Gemini-based parser, ignores domain)
        parser = get_parser(domain)

        is_tier2 = pid in TIER2_IDS

        try:
            if is_tier2:
                raw_price = parser.extract_min_price(html, url)
            else:
                raw_price = parser.extract_price(html, url)
        except Exception as exc:
            logger.warning("PARSE ERROR [%s] %s: %s", pid, domain, exc)
            failed_skipped.append((pid, f"parse error: {exc}"))
            # Rate limit sleep even on error
            time.sleep(GEMINI_SLEEP)
            continue

        # Rate limiting — sleep after each Gemini call
        time.sleep(GEMINI_SLEEP)

        price = _validate_price(raw_price)
        checked_count += 1

        if price is None:
            logger.warning("SKIP [%s]: no valid price found (raw=%r)", pid, raw_price)
            failed_skipped.append((pid, f"no valid price (raw={raw_price!r})"))
            continue

        current_min = product.get("price_min")
        try:
            current_min_int = int(float(current_min)) if current_min is not None else None
        except (TypeError, ValueError):
            current_min_int = None

        # Sanity check: reject implausible price changes
        if current_min_int is not None and current_min_int > 0 and price != current_min_int:
            if not _is_sane_change(current_min_int, price):
                ratio = price / current_min_int
                logger.warning(
                    "SUSPICIOUS [%s]: %d -> %d (ratio %.2fx), SKIPPING",
                    pid, current_min_int, price, ratio,
                )
                suspicious.append((pid, current_min_int, price, ratio))
                # Do NOT update any fields — not even last_checked (we don't trust this fetch)
                continue

        if current_min_int is not None and price == current_min_int:
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
    print("=" * 40)
    print("Price Check Summary")
    print("=" * 40)
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
    print(f"SUSPICIOUS — price change too large, skipped for safety ({len(suspicious)}):")
    if suspicious:
        for pid, old_p, new_p, ratio in suspicious:
            print(f"  - {pid}: HK${old_p:,} → HK${new_p:,} ({ratio:.2f}x) *** manual review needed ***")
    else:
        print("  (none)")
    print("=" * 40)


if __name__ == "__main__":
    main()
