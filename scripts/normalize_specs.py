"""Normalize specs across all 58 products.

Phase A:
 1. Split each product's `specs` / `specs_en` into:
    - measurable specs (according to category schema), with normalized format
    - features (everything else) → moves to new fields `features` / `features_en`
 2. Apply format rules:
    - Full-width colon ： between label and value (zh only; English uses ': ')
    - En-dash – for numeric ranges (not - or —)
    - Options: '16" / 18"' with spaces
    - Numbers + unit zh: no space (12.9kg)
    - Numbers + unit en: one space (12.9 kg)

This is non-destructive: writes products.json.new for diff review.
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from category_schema import SCHEMA, LABEL_ZH_TO_EN, LABEL_EN_TO_ZH, LABEL_ZH_ALIAS


SOURCE = "/tmp/ych-occu-rehab-aids-tracker/products.json"
OUTPUT = "/tmp/ych-occu-rehab-aids-tracker/products.json.new"


def normalize_value(v: str, lang: str = "zh") -> str:
    """Apply unit/range/option formatting rules to a spec value."""
    s = v.strip()
    # Convert hyphen/em-dash ranges to en-dash: '17.5"-19.5"' -> '17.5"–19.5"'
    # Match optional " or units between numbers
    s = re.sub(r'(\d(?:\.\d+)?["\']?)\s*[-—–]\s*(\d(?:\.\d+)?)', r'\1–\2', s)

    # Normalize option separators: '16"/18"' or '16" / 18"' -> '16" / 18"'
    # Only convert / surrounded by alphanumerics/inches
    s = re.sub(r'(["\'a-zA-Z0-9])\s*/\s*(["\'a-zA-Z0-9])', r'\1 / \2', s)
    s = re.sub(r' +', ' ', s)

    # Unit spacing:
    if lang == "zh":
        # Remove spaces between number and common units (kg, lb, cm, mm, g, cc, kPa)
        s = re.sub(r'(\d(?:\.\d+)?)\s+(kg|lb|cm|mm|m|g|cc|kPa|公斤|公分)\b', r'\1\2', s)
    else:
        # Ensure exactly one space between number and unit
        s = re.sub(r'(\d(?:\.\d+)?)(kg|lb|cm|mm|g|cc|kPa)\b', r'\1 \2', s)
        s = re.sub(r' +', ' ', s)

    return s.strip()


def split_label_value(spec: str):
    """Return (label, value) or (None, full_string) if no colon.

    Matches half-width ':', full-width '：', and small full-width '﹕' colons.
    """
    m = re.match(r'^([^:：﹕]+)[:：﹕]\s*(.*)$', spec)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, spec.strip()


def process_product(p: dict) -> dict:
    cat = p.get("category", "")
    schema = SCHEMA.get(cat)
    if schema is None:
        # Unknown category — leave alone
        return p

    allowed_labels = set(schema["core"]) | set(schema["optional"])

    new_specs_zh, new_features_zh = [], []
    new_specs_en, new_features_en = [], []

    # Build dict {zh_label: zh_value}
    zh_dict, en_dict = {}, {}

    for s in p.get("specs", []):
        lbl, val = split_label_value(s)
        # Apply zh alias mapping
        canonical = LABEL_ZH_ALIAS.get(lbl, lbl) if lbl else None
        if canonical in allowed_labels:
            # Only set if not already populated (preserves earlier supplier-fetch merges)
            if canonical not in zh_dict:
                zh_dict[canonical] = normalize_value(val, "zh")
        else:
            new_features_zh.append(s)

    for s in p.get("specs_en", []):
        lbl, val = split_label_value(s)
        zh_lbl = LABEL_EN_TO_ZH.get(lbl) if lbl else None
        if zh_lbl in allowed_labels:
            if zh_lbl not in en_dict:
                en_dict[zh_lbl] = normalize_value(val, "en")
        else:
            new_features_en.append(s)

    # Emit specs in canonical order: core first, then optional that are present
    order = schema["core"] + [k for k in schema["optional"] if k in zh_dict or k in en_dict]
    for k in order:
        if k in zh_dict:
            new_specs_zh.append(f"{k}：{zh_dict[k]}")
        if k in en_dict:
            new_specs_en.append(f"{LABEL_ZH_TO_EN.get(k, k)}: {en_dict[k]}")

    p["specs"] = new_specs_zh
    p["specs_en"] = new_specs_en
    p["features"] = new_features_zh
    p["features_en"] = new_features_en
    return p


def main():
    with open(SOURCE, encoding="utf-8") as f:
        data = json.load(f)

    items = data["products"] if isinstance(data, dict) and "products" in data else data

    missing_report = []
    for p in items:
        process_product(p)
        # Flag missing core specs
        cat = p.get("category", "")
        schema = SCHEMA.get(cat)
        if schema:
            zh_labels = {re.match(r'^([^：]+)', s).group(1) for s in p["specs"]}
            missing = [k for k in schema["core"] if k not in zh_labels]
            if missing:
                missing_report.append((p["id"], cat, missing))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUTPUT}")
    print(f"\n=== Missing core specs ({len(missing_report)} products) ===")
    for pid, cat, missing in missing_report:
        print(f"  [{pid}] ({cat}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
