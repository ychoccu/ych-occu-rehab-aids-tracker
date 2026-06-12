"""
Rebuild ych_rehab_aids_standalone.html by embedding base64 images
and the current products.json into the index.html SPA.

Can be run directly:  python scripts/rebuild_html.py
Or imported and called as rebuild_html.rebuild()
"""

import base64
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGES = REPO / "images"
INDEX = REPO / "index.html"
PJSON = REPO / "products.json"
OUTPUT = REPO / "ych_rehab_aids_standalone.html"

MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def to_data_uri(p: Path) -> str:
    mime = MIME.get(p.suffix.lower(), "application/octet-stream")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def rebuild():
    # Build image map: filename → data URI
    image_map: dict[str, str] = {
        p.name: to_data_uri(p)
        for p in IMAGES.iterdir()
        if p.is_file()
    }

    # Load and patch products (replace image_url with data URIs)
    products = json.loads(PJSON.read_text(encoding="utf-8"))
    for p in products:
        url = p.get("image_url", "")
        if not url:
            continue
        m = re.match(r"\.?/?images/(.+)$", url)
        if m and m.group(1) in image_map:
            p["image_url"] = image_map[m.group(1)]

    # Read and patch HTML (replace src="images/..." with data URIs)
    html = INDEX.read_text(encoding="utf-8")

    def rep(m: re.Match) -> str:
        src = m.group(1)
        mm = re.match(r"\.?/?images/(.+)$", src)
        if mm and mm.group(1) in image_map:
            return m.group(0).replace(src, image_map[mm.group(1)])
        return m.group(0)

    html = re.sub(r'src=["\']([^"\']*images/[^"\']+)["\']', rep, html)

    # Inject embedded products + fetch override
    inject = f"""<script>
window.__EMBEDDED_PRODUCTS__ = {json.dumps(products, ensure_ascii=False)};
(function() {{
  var origFetch = window.fetch;
  window.fetch = function(url, opts) {{
    if (typeof url === 'string' && url.indexOf('products.json') !== -1) {{
      return Promise.resolve({{
        ok: true, status: 200,
        json: function() {{ return Promise.resolve(window.__EMBEDDED_PRODUCTS__); }},
        text: function() {{ return Promise.resolve(JSON.stringify(window.__EMBEDDED_PRODUCTS__)); }}
      }});
    }}
    return origFetch.apply(this, arguments);
  }};
}})();
</script>
"""

    if "<head>" in html:
        html = html.replace("<head>", "<head>\n" + inject, 1)
    else:
        html = html.replace("</head>", inject + "</head>", 1)

    OUTPUT.write_text(html, encoding="utf-8")
    size_mb = OUTPUT.stat().st_size / 1024 / 1024
    print(f"Wrote {OUTPUT}  size={size_mb:.2f}MB")


if __name__ == "__main__":
    rebuild()
