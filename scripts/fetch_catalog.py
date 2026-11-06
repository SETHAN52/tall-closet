#!/usr/bin/env python3
"""Fetch public Shopify product JSON from tall-friendly stores and write data/items.json."""

from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
UA = (
    "FamilyTallCatalog/1.0 "
    "(personal read-only family catalog; "
    "+https://github.com/SETHAN52/tall-closet)"
)
TIMEOUT = 30
PAGE_LIMIT = 250
MAX_PAGES = 40
MAX_RETRIES = 6

# Approximate FX used only for cross-store price sorting.
FX_TO_USD = {"USD": 1.0, "GBP": 1.30, "EUR": 1.08, "CAD": 0.72}

SOURCES = [
    {
        "id": "american-tall",
        "name": "American Tall",
        "base": "https://americantall.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "tall-mens-and-womens-clothing",
        "dedicated": True,
        "default_gender": None,
    },
    {
        "id": "2tall",
        "name": "2tall",
        "base": "https://www.2tall.com",
        "currency": "GBP",
        "mode": "collection",
        "collection": "tall-mens-clothing",
        "dedicated": True,
        "default_gender": "men",
    },
    {
        "id": "tallslim-tees",
        "name": "TallSlim Tees",
        "base": "https://tallslimtees.com",
        "currency": "USD",
        "mode": "products",
        "dedicated": True,
        "default_gender": "men",
    },
    {
        "id": "just-tall",
        "name": "Just Tall",
        "base": "https://justtall.com",
        "currency": "GBP",
        "mode": "collection",
        "collection": "mens-tall-slim-tops",
        "dedicated": True,
        "default_gender": "men",
    },
    {
        "id": "alloy-apparel",
        "name": "Alloy Apparel",
        "base": "https://www.alloyapparel.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "womens-tall-essentials",
        "dedicated": True,
        "default_gender": "women",
    },
    {
        "id": "tall-size",
        "name": "Tall Size",
        "base": "https://www.tallsize.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "all",
        "dedicated": True,
        "default_gender": "women",
    },
    {
        "id": "amalli-talli",
        "name": "Amalli Talli",
        "base": "https://amallitalli.com",
        "currency": "USD",
        "mode": "products",
        "dedicated": True,
        "default_gender": "women",
    },
    {
        "id": "wildflower-club",
        "name": "The Wildflower Club",
        "base": "https://www.thewildflowerclub.com",
        "currency": "EUR",
        "mode": "products",
        "dedicated": True,
        "default_gender": "women",
    },
    {
        "id": "true-classic",
        "name": "True Classic",
        "base": "https://www.trueclassictees.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "tall-fit",
        "dedicated": True,
        "default_gender": "men",
    },
    {
        "id": "duer",
        "name": "DUER",
        "base": "https://www.duer.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "length-34",
        "dedicated": False,
        "default_gender": None,
        "note": "34-inch inseam collection",
    },
    {
        "id": "haggar",
        "name": "Haggar",
        "base": "https://www.haggar.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "big-tall",
        "dedicated": False,
        "default_gender": "men",
    },
    {
        "id": "eddie-bauer",
        "name": "Eddie Bauer",
        "base": "https://www.eddiebauer.com",
        "currency": "USD",
        "mode": "collection",
        "collection": "all-products",
        "dedicated": False,
        "default_gender": None,
    },
]

SKIP_TITLE = re.compile(
    r"gift\s*card|order protection|extended warranty|shipping insurance|"
    r"fuel surcharge|not a product|store credit",
    re.I,
)
LONG_SLEEVE = re.compile(r"long[\s-]?sleeve", re.I)
TALL_WORD = re.compile(
    r"\b(extra[\s-]?tall|x-?tall|xtall|tall)\b|\b[2-6]?xl?t\b|\b[lms]t\b|"
    r"\btall fit\b|\btall size\b",
    re.I,
)
INSEAM = re.compile(
    r"\b(3[4-9]|40|42)\s*(?:\"|”|in(?:ch(?:es)?)?|inseam)?\b|"
    r"\binseam[^0-9]{0,8}(3[4-9]|40|42)\b",
    re.I,
)
SIZE_INSEAM = re.compile(r"\b(3[4-9]|40|42)(?:\"|”)?\b")
GENDER_MEN = re.compile(r"\b(men|mens|men's|male|guy|gents?)\b", re.I)
GENDER_WOMEN = re.compile(
    r"\b(women|womens|women's|woman|ladies|lady|female|girls?)\b", re.I
)


def request_json(url: str) -> dict | list | None:
    last_err = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 503, 502, 520, 521, 522, 524):
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = min(180, 12 * (2 ** attempt)) + random.uniform(0, 4)
                print(f"  {e.code} on {url} — waiting {wait:.0f}s (try {attempt + 1})", flush=True)
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            wait = min(60, 5 * (2 ** attempt))
            print(f"  error {e!r} — waiting {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Failed after retries: {url} ({last_err})")


def paginate(url_for_page) -> list[dict]:
    products = []
    for page in range(1, MAX_PAGES + 1):
        url = url_for_page(page)
        data = request_json(url)
        if not data:
            break
        batch = data.get("products") if isinstance(data, dict) else None
        if not batch:
            break
        products.extend(batch)
        print(f"    page {page}: +{len(batch)} (total {len(products)})", flush=True)
        if len(batch) < PAGE_LIMIT:
            break
        time.sleep(0.85)
    return products


def fetch_source(src: dict) -> list[dict]:
    base = src["base"].rstrip("/")
    if src["mode"] == "collection":
        handle = src["collection"]
        products = paginate(
            lambda p: f"{base}/collections/{handle}/products.json?limit={PAGE_LIMIT}&page={p}"
        )
        if not products:
            print("    collection empty, falling back to products.json", flush=True)
            products = paginate(
                lambda p: f"{base}/products.json?limit={PAGE_LIMIT}&page={p}"
            )
        return products
    return paginate(lambda p: f"{base}/products.json?limit={PAGE_LIMIT}&page={p}")


def blob_of(product: dict) -> str:
    tags = product.get("tags") or ""
    if isinstance(tags, list):
        tags = " ".join(tags)
    variants = product.get("variants") or []
    var_text = " ".join(
        f"{v.get('title','')} {v.get('option1','')} {v.get('option2','')} {v.get('option3','')}"
        for v in variants
    )
    return " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("product_type") or ""),
            str(product.get("vendor") or ""),
            tags,
            var_text,
        ]
    )


def looks_tall(product: dict, dedicated: bool) -> bool:
    if dedicated:
        return True
    text = blob_of(product)
    text_no_sleeve = LONG_SLEEVE.sub(" ", text)
    if TALL_WORD.search(text_no_sleeve):
        return True
    if INSEAM.search(text_no_sleeve):
        return True
    return False


def detect_gender(product: dict, default: str | None) -> str:
    title = str(product.get("title") or "")
    tags = product.get("tags") or ""
    if isinstance(tags, list):
        tags = " ".join(tags)
    ptype = str(product.get("product_type") or "")
    text = f"{title} {tags} {ptype}"
    men = bool(GENDER_MEN.search(text))
    women = bool(GENDER_WOMEN.search(text))
    if men and not women:
        return "men"
    if women and not men:
        return "women"
    if men and women:
        # Titles like "for Tall Men" vs "for Tall Women" — prefer the closer phrase.
        if re.search(r"for tall women|women'?s|ladies", text, re.I):
            if not re.search(r"for tall men|men'?s", title, re.I):
                return "women"
        if re.search(r"for tall men|men'?s", title, re.I):
            return "men"
        return "unisex"
    return default or "unisex"


def detect_category(product: dict) -> str:
    text = f"{product.get('title','')} {product.get('product_type','')}".lower()
    rules = [
        ("shoes", r"\b(shoe|boot|sneaker|heel|sandal|loafer|oxford|pump|footwear)\b"),
        ("accessories", r"\b(hat|cap|beanie|belt|bag|scarf|glove|wallet|sock|tie|jewelry|watch)\b"),
        ("underwear", r"\b(underwear|brief|boxer|bra|bralette|lingerie|intimate|undies)\b"),
        ("swim", r"\b(swim|bikini|trunks?|rashguard)\b"),
        ("sleepwear", r"\b(pajama|pyjama|sleepwear|nightgown|robe|dressing gown)\b"),
        ("dresses", r"\b(dress|gown)\b"),
        ("jumpsuits", r"\b(jumpsuit|romper|overall)\b"),
        ("skirts", r"\bskirt\b"),
        ("jeans", r"\bjeans?\b"),
        ("pants", r"\b(pants?|trousers?|chinos?|leggings?|joggers?|sweatpants?)\b"),
        ("shorts", r"\bshorts?\b"),
        ("outerwear", r"\b(jacket|coat|parka|puffer|vest|anorak|trench|windbreaker|raincoat)\b"),
        ("activewear", r"\b(active|athletic|yoga|workout|sport|performance)\b"),
        ("hoodies", r"\b(hoodie|sweatshirt|crewneck|quarter[-\s]?zip)\b"),
        ("sweaters", r"\b(sweater|jumper|cardigan|knitwear|pullover)\b"),
        ("shirts", r"\b(button[-\s]?down|oxford|dress shirt|blouse|flannel|henley|polo)\b"),
        ("tops", r"\b(tee|t-shirt|tshirt|tank|top|shirt)\b"),
    ]
    for name, pat in rules:
        if re.search(pat, text):
            return name
    return "other"


def parse_price(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def cdn_thumb(src: str | None) -> str | None:
    if not src:
        return None
    return re.sub(r"\.(jpg|jpeg|png|webp)(\?|$)", r"_400x.\1\2", src, count=1, flags=re.I)


def extract_sizes(product: dict) -> list[str]:
    options = product.get("options") or []
    size_names = {
        "size",
        "sizes",
        "length",
        "inseam",
        "tall size",
        "height",
        "fit",
        "length/inseam",
    }
    collected: list[str] = []
    for opt in options:
        name = str(opt.get("name") or "").strip().lower()
        if name in size_names or "size" in name or "inseam" in name or "length" in name:
            for val in opt.get("values") or []:
                val = str(val).strip()
                if val and val.lower() not in {"default title", "os", "one size"}:
                    collected.append(val)
    if not collected:
        for v in product.get("variants") or []:
            if v.get("available") is False:
                continue
            title = str(v.get("title") or "").strip()
            if title and title.lower() != "default title":
                collected.append(title)
    # Prefer values that look like tall sizing, then unique preserve order.
    seen = set()
    out = []
    for val in collected:
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
    # Keep the list readable.
    if len(out) > 18:
        # Prefer ones mentioning tall or a long inseam.
        ranked = [
            v
            for v in out
            if re.search(r"tall|xt|xlt|\b(3[4-9]|40|42)\b", v, re.I)
        ]
        rest = [v for v in out if v not in ranked]
        out = (ranked + rest)[:18]
    return out


def normalize(product: dict, src: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or SKIP_TITLE.search(title):
        return None
    if not looks_tall(product, src.get("dedicated", False)):
        return None
    variants = product.get("variants") or []
    prices = [parse_price(v.get("price")) for v in variants]
    prices = [p for p in prices if p is not None]
    compares = [parse_price(v.get("compare_at_price")) for v in variants]
    compares = [c for c in compares if c is not None]
    if not prices:
        return None
    price = min(prices)
    compare_at = max(compares) if compares else None
    on_sale = bool(compare_at and compare_at > price + 0.01)
    images = product.get("images") or []
    image = None
    if images:
        image = images[0].get("src")
    elif product.get("image"):
        image = (product.get("image") or {}).get("src")
    gender = detect_gender(product, src.get("default_gender"))
    handle = product.get("handle") or ""
    url = f"{src['base'].rstrip('/')}/products/{handle}" if handle else src["base"]
    published = product.get("published_at") or product.get("created_at") or ""
    currency = src["currency"]
    usd = round(price * FX_TO_USD.get(currency, 1.0), 2)
    return {
        "id": f"{src['id']}-{product.get('id')}",
        "title": title,
        "store": src["name"],
        "store_id": src["id"],
        "url": url,
        "image": cdn_thumb(image) or image,
        "price": price,
        "compare_at": compare_at if on_sale else None,
        "currency": currency,
        "price_usd": usd,
        "sale": on_sale,
        "gender": gender,
        "category": detect_category(product),
        "sizes": extract_sizes(product),
        "published_at": published,
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    seen = set()
    reports = []
    started = datetime.now(timezone.utc)

    for src in SOURCES:
        print(f"\n== {src['name']} ({src['base']}) ==", flush=True)
        t0 = time.time()
        error = None
        raw = []
        kept = 0
        try:
            raw = fetch_source(src)
            for product in raw:
                item = normalize(product, src)
                if not item:
                    continue
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                items.append(item)
                kept += 1
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"  FAILED: {error}", flush=True)
        elapsed = round(time.time() - t0, 1)
        report = {
            "id": src["id"],
            "name": src["name"],
            "fetched": len(raw),
            "kept": kept,
            "seconds": elapsed,
            "error": error,
            "ok": error is None and kept > 0,
        }
        reports.append(report)
        print(f"  fetched {len(raw)}, kept {kept} in {elapsed}s", flush=True)
        time.sleep(1.4)

    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    finished = datetime.now(timezone.utc)
    meta = {
        "generated_at": finished.isoformat(),
        "item_count": len(items),
        "stores": reports,
        "ok_stores": sum(1 for r in reports if r["ok"]),
        "failed_stores": [r for r in reports if not r["ok"]],
        "duration_seconds": round((finished - started).total_seconds(), 1),
    }
    (DATA_DIR / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n==== summary ====")
    for r in reports:
        status = "OK" if r["ok"] else "FAIL"
        print(f"  {status:4} {r['name']:22} fetched={r['fetched']:4} kept={r['kept']:4} {r['error'] or ''}")
    print(f"Wrote {len(items)} items to data/items.json")
    return 0 if any(r["ok"] for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
