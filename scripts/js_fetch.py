"""
JavaScript-rendered page fetcher using Playwright.
For sites like justmed.com.hk that inject prices via JS.
"""
import logging
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger(__name__)

JS_RENDERED_DOMAINS = {
    "justmed.com.hk",
    "www.justmed.com.hk",
}


def needs_js_render(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return host in JS_RENDERED_DOMAINS
    except Exception:
        return False


def fetch_html_with_browser(url: str, timeout_ms: int = 30000) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-HK",
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                # Wait for JS-injected #price div (justmed.com.hk).
                # If it appears, return immediately; else fall through to fixed wait.
                try:
                    page.wait_for_function(
                        "() => { const el = document.querySelector('#price .product-price'); "
                        "return el && el.innerText.trim().length > 0; }",
                        timeout=6000,
                    )
                except Exception:
                    pass
                # Extra buffer so other lazy content (e.g. carousels) settles.
                page.wait_for_timeout(2000)
                html = page.content()
                logger.info("BROWSER FETCH OK [%s]: %d chars", url, len(html))
                return html
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("BROWSER FETCH FAIL [%s]: %s", url, exc)
        return None
