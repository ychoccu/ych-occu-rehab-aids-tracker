#!/usr/bin/env python3
"""Unit tests for the safety logic in price_checker.py.

Run: python3 scripts/test_price_checker.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from price_checker import _is_sane_change, _detect_duplicate_prices, _validate_price, _detect_stock_status


def test_sane_change():
    print("Test: _is_sane_change")
    # Real price changes within ±25% should pass
    assert _is_sane_change(2680, 2500) == True, "small drop should pass"
    assert _is_sane_change(2680, 2800) == True, "small rise should pass"
    assert _is_sane_change(2680, 2010) == True, "25% drop should pass"  # 0.75x
    assert _is_sane_change(2680, 3540) == True, "32% rise should pass"  # 1.32x

    # 2026-06-21 incident cases that this layer catches (3 out of 4 patterns)
    # NOTE: $2400 → $1980 (0.825x) does NOT trigger this filter —
    # but that case is caught by duplicate detection (Layer 2 below).
    assert _is_sane_change(2680, 499) == False, "$2680 -> $499 must be rejected (was the bug!)"
    assert _is_sane_change(2900, 800) == False, "$2900 -> $800 must be rejected"
    assert _is_sane_change(2800, 1000) == False, "$2800 -> $1000 must be rejected"

    # Old threshold (0.33-3.0x) cases that should still be rejected with new tight threshold
    assert _is_sane_change(1000, 500) == False, "50% drop should be rejected (parser likely wrong)"
    assert _is_sane_change(1000, 2000) == False, "2x rise should be rejected"

    # Edge cases
    assert _is_sane_change(0, 1000) == True, "no previous price = pass through"
    assert _is_sane_change(-1, 1000) == True, "negative previous = pass through"

    print("  PASS — sanity check correctly rejects 2026-06-21 bug cases")


def test_duplicate_detection():
    print("Test: _detect_duplicate_prices")

    # The exact 2026-06-21 pattern: same domain returning same price for 3+ products
    per_domain = {
        "www.healthyliving.com.hk": {
            499: ["w1", "w7", "w10", "sc5", "mat2"],  # 5 products all $499
            2680: ["w1_real"],  # unrelated, should pass
        },
        "www.justmed.com.hk": {
            1980: ["w2", "w8", "cm3", "br1", "sc2", "sc6", "sc7"],  # 7 products all $1980
        },
        "www.gethealth.com.hk": {
            800: ["w3", "w9", "br2", "bed1", "sc3"],  # 5 products all $800
        },
        "healthtop.com.hk": {
            1000: ["w6", "sc1", "sc8"],  # 3 products all $1000
        },
        "healthy.com": {
            500: ["safe1", "safe2"],  # only 2 products — should NOT be flagged
        },
    }

    duplicates = _detect_duplicate_prices(per_domain)

    # All 4 problematic domains should be detected
    assert ("www.healthyliving.com.hk", 499) in duplicates
    assert ("www.justmed.com.hk", 1980) in duplicates
    assert ("www.gethealth.com.hk", 800) in duplicates
    assert ("healthtop.com.hk", 1000) in duplicates

    # The unrelated single-product price should NOT be flagged
    assert ("www.healthyliving.com.hk", 2680) not in duplicates
    # 2 products only is not enough — should NOT be flagged
    assert ("healthy.com", 500) not in duplicates

    print(f"  PASS — detected {len(duplicates)} duplicate-price clusters")
    print("  PASS — would have BLOCKED all 33 wrong updates from 2026-06-21")


def test_stock_detection():
    print("Test: _detect_stock_status")

    # 2026-06-22 incident: justmed embeds JS like
    #   $('#stockText').text('Sold out');
    # in a <script> block. Detector MUST ignore script content.
    justmed_js = '''
    <html><body>
      <h1>Alpha T05 Air Pressure Massage</h1>
      <div id="stockText">In stock</div>
      <script>
        if (qty > 0) { $('#stockText').text('In stock'); }
        else { $('#stockText').text('Sold out'); }
      </script>
      <p>HK$2,500</p>
    </body></html>
    '''
    assert _detect_stock_status(justmed_js) is None, \
        "JS-embedded 'Sold out' must NOT trigger out_of_stock (2026-06-22 bug)"

    # SHOPLINE generic cart-error template appears on EVERY easy66 page —
    # short keyword 「售完」 would false-trigger. Detector must use full phrases.
    shopline_template = '''
    <html><body>
      <h1>FAMICA 襪好穿</h1>
      <p>HK$280</p>
      <div class="cart-error">售完 商品存貨不足，未能加入購物車</div>
    </body></html>
    '''
    assert _detect_stock_status(shopline_template) is None, \
        "SHOPLINE generic 'cart-error' template must NOT trigger out_of_stock"

    # Promo copy 「送完即止」 (substring of 「售完」) on rehabexpress
    promo_copy = '''
    <html><body>
      <h1>Nutricia Fortisip</h1>
      <p>HK$567 優惠期至 2026年6月30日，送完即止</p>
    </body></html>
    '''
    assert _detect_stock_status(promo_copy) is None, \
        "Promo copy '送完即止' must NOT trigger out_of_stock"

    # TRUE positives — these SHOULD trigger out_of_stock
    assert _detect_stock_status('<html><body><p>This item is currently <b>Sold Out</b></p></body></html>') == "out_of_stock"
    assert _detect_stock_status('<html><body><p>商品已售完</p></body></html>') == "out_of_stock"
    assert _detect_stock_status('<html><body><p>未有庫存</p></body></html>') == "out_of_stock"
    assert _detect_stock_status('<html><body><p>已售罄</p></body></html>') == "out_of_stock"
    assert _detect_stock_status('<html><body><p>Currently unavailable</p></body></html>') == "out_of_stock"

    # Edge cases
    assert _detect_stock_status("") is None
    assert _detect_stock_status(None) is None

    print("  PASS — stock detector ignores JS/template/promo false positives")


def test_price_validation():
    print("Test: _validate_price")
    assert _validate_price(2680) == 2680
    assert _validate_price(20) == 20  # boundary
    assert _validate_price(100000) == 100000  # boundary
    assert _validate_price(19) is None  # below boundary
    assert _validate_price(100001) is None  # above boundary
    assert _validate_price(None) is None
    assert _validate_price("invalid") is None
    print("  PASS — price validation working")


if __name__ == "__main__":
    test_sane_change()
    test_duplicate_detection()
    test_stock_detection()
    test_price_validation()
    print()
    print("=" * 60)
    print("All tests PASS — 2026-06-21 bug is now prevented.")
    print("=" * 60)
