"""
Single Gemini-based extractor for all domains.
"""
from .gemini_extract import extract_price as _gemini_extract


def get_parser(domain: str):
    """Returns a unified parser callable for any domain."""
    return _UnifiedParser()


class _UnifiedParser:
    def extract_price(self, html: str, url: str) -> int | None:
        return _gemini_extract(html, url, tier=1)

    def extract_min_price(self, html: str, url: str) -> int | None:
        return _gemini_extract(html, url, tier=2)
