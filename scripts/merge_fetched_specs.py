"""Merge wide_browse extracted_specs into products.json.new

Reads products.json.new (normalized) + fetched specs from wide_browse output.
Inserts the new measurable specs into specs[] / specs_en[] in the canonical
order defined by category_schema.SCHEMA.
"""
import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from category_schema import SCHEMA, LABEL_ZH_TO_EN

PRODUCTS = "/tmp/ych-occu-rehab-aids-tracker/products.json.new"
FETCH    = "/home/user/workspace/wide/browse_results_mqg7fgih.json"


def main():
    with open(PRODUCTS, encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else data["products"]

    with open(FETCH, encoding="utf-8") as f:
        fetched = json.load(f)["results"]

    # Build {pid: [extracted_spec_objs]}
    pid_to_extracted = {}
    for row in fetched:
        pid = row["Product ID"]
        pid_to_extracted[pid] = row.get("Extracted specs") or []

    updates = 0
    for p in items:
        pid = p["id"]
        if pid not in pid_to_extracted:
            continue
        cat = p.get("category", "")
        schema = SCHEMA.get(cat)
        if not schema:
            continue

        # Build dicts of current specs by label
        zh_dict, en_dict = {}, {}
        for s in p.get("specs", []):
            m = re.match(r"^([^：]+)：\s*(.*)$", s)
            if m:
                zh_dict[m.group(1).strip()] = m.group(2).strip()
        for s in p.get("specs_en", []):
            m = re.match(r"^([^:]+):\s*(.*)$", s)
            if m:
                # find zh label by reverse lookup
                en_lbl = m.group(1).strip()
                zh_lbl = next((zh for zh, en in LABEL_ZH_TO_EN.items() if en == en_lbl), None)
                if zh_lbl:
                    en_dict[zh_lbl] = m.group(2).strip()

        # Merge fetched specs
        for e in pid_to_extracted[pid]:
            zh_lbl = e.get("zh_label", "").strip()
            zh_val = e.get("zh_value", "").strip()
            en_val = e.get("en_value", "").strip()
            if not zh_lbl or not zh_val:
                continue
            if zh_lbl in zh_dict:
                continue  # already exists, don't overwrite
            zh_dict[zh_lbl] = zh_val
            if en_val:
                en_dict[zh_lbl] = en_val
            updates += 1

        # Re-emit specs in canonical order
        order = schema["core"] + [k for k in schema["optional"] if k in zh_dict or k in en_dict]
        new_specs_zh, new_specs_en = [], []
        for k in order:
            if k in zh_dict:
                new_specs_zh.append(f"{k}：{zh_dict[k]}")
            if k in en_dict:
                en_lbl = LABEL_ZH_TO_EN.get(k, k)
                new_specs_en.append(f"{en_lbl}: {en_dict[k]}")
        p["specs"] = new_specs_zh
        p["specs_en"] = new_specs_en

    # Write merged
    with open(PRODUCTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Merged {updates} new specs into {PRODUCTS}")

    # Report remaining missing
    print("\n=== Remaining missing core specs ===")
    for p in items:
        cat = p.get("category", "")
        schema = SCHEMA.get(cat)
        if not schema:
            continue
        zh_labels = {re.match(r"^([^：]+)", s).group(1) for s in p["specs"]}
        missing = [k for k in schema["core"] if k not in zh_labels]
        if missing:
            print(f"  [{p['id']}] ({cat}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
