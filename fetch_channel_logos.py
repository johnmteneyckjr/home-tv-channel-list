#!/usr/bin/env python3
"""
Fetch small channel logos for a DISH lineup.

Usage:
  1) Edit channels.csv if needed (search_hint column).
  2) Optionally add any explicit URLs to overrides.csv.
  3) pip install -r requirements.txt
  4) python fetch_channel_logos.py

This module is also importable and exposes `fetch_channel_logos(...)` so other
scripts (like build_tv_channel_sheet.py) can request logos on demand.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
from typing import Callable, Dict, Optional

import requests
from PIL import Image

TARGET_PX = int(os.getenv("TARGET_PX", "128"))
TIMEOUT = 20
UA = "JT-Channel-Logo-Fetcher/1.0 (+for private lineup UI; contact local admin)"

BASE_WP = "https://en.wikipedia.org/w/api.php"
BASE_WD = "https://www.wikidata.org/w/api.php"
BASE_COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width={}"


def nap():
    """Sleep briefly so we are polite to the public APIs."""
    time.sleep(0.4)


def read_overrides(path: Optional[str] = "overrides.csv") -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                code = (row.get("code") or "").strip()
                url = (row.get("direct_image_url") or "").strip()
                if code and url:
                    overrides[code] = url
    return overrides


def request_json(url, params=None):
    headers = {"User-Agent": UA}
    resp = requests.get(url, params=params or {}, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def wp_search_title(query: str) -> Optional[str]:
    if not query:
        return None
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "format": "json",
    }
    data = request_json(BASE_WP, params)
    hits = data.get("query", {}).get("search", [])
    if hits:
        return hits[0]["title"]
    return None


def wp_get_wikibase_item(title: str) -> Optional[str]:
    if not title:
        return None
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "format": "json",
    }
    data = request_json(BASE_WP, params)
    pages = data.get("query", {}).get("pages", {})
    for _, p in pages.items():
        pp = p.get("pageprops", {})
        if "wikibase_item" in pp:
            return pp["wikibase_item"]
    return None


def wd_get_logo_filename(qid: str) -> Optional[str]:
    if not qid:
        return None
    params = {"action": "wbgetclaims", "entity": qid, "property": "P154", "format": "json"}
    data = request_json(BASE_WD, params)
    claims = data.get("claims", {}).get("P154", [])
    for c in claims:
        mainsnak = c.get("mainsnak", {})
        dv = mainsnak.get("datavalue", {}).get("value")
        if isinstance(dv, str):
            return dv
        if isinstance(dv, dict) and "title" in dv:
            return dv["title"]
    return None


def commons_file_url(filename: str, width: int) -> str:
    safe = urllib.parse.quote(filename.replace(" ", "_"))
    return BASE_COMMONS_FILEPATH.format(safe, width)


def github_tvlogos_search(term: str) -> Optional[str]:
    # Best-effort: search the "tv-logo/tv-logos" repository for a PNG/SVG in US paths
    q = f"{term} repo:tv-logo/tv-logos"
    url = "https://api.github.com/search/code"
    try:
        data = request_json(url, {"q": q})
        items = data.get("items", [])
        for it in items:
            path = it.get("path", "")
            if "United-States" in path or "/US/" in path or "/United States/" in path:
                raw_url = (
                    it.get("html_url", "")
                    .replace("github.com", "raw.githubusercontent.com")
                    .replace("/blob/", "/")
                )
                return raw_url
        if items:
            raw_url = (
                items[0]
                .get("html_url", "")
                .replace("github.com", "raw.githubusercontent.com")
                .replace("/blob/", "/")
            )
            return raw_url
    except Exception:
        return None
    return None


def normalize_png(data: bytes, target_px: int) -> bytes:
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    w, h = im.size
    scale = target_px / max(w, h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    im = im.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (target_px, target_px), (0, 0, 0, 0))
    ox = (target_px - new_w) // 2
    oy = (target_px - new_h) // 2
    canvas.paste(im, (ox, oy), im)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def download(url: str) -> Optional[bytes]:
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        return None
    return None


def guess_station_title(code: str) -> str:
    if re.fullmatch(r"[KW][A-Z]{3}\d+", code):
        m = re.match(r"([KW][A-Z]{3})(\d+)", code)
        if m:
            return f"{m.group(1)}-DT{m.group(2)}"
    if re.fullmatch(r"[KW][A-Z0-9]{3,5}", code):
        return f"{code}-TV"
    return code


def fetch_channel_logos(
    channels_csv: str = "channels.csv",
    overrides_csv: Optional[str] = "overrides.csv",
    output_dir: str = "./output",
    target_px: Optional[int] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    """
    Fetch logos for all rows in channels_csv.

    Returns a mapping of channel code to the generated PNG path.
    """
    px = int(target_px or TARGET_PX)
    log = logger or print
    out_dir = os.path.abspath(output_dir)
    os.makedirs(out_dir, exist_ok=True)
    overrides = read_overrides(overrides_csv)
    log(f"[i] TARGET_PX={px}, output -> {out_dir}")

    with open(channels_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    success = 0
    fail = 0
    written: Dict[str, str] = {}

    for row in rows:
        num = (row.get("number") or "").strip()
        code = (row.get("code") or row.get("name") or "").strip()
        if not num or not code:
            continue
        ch_type = (row.get("type") or "network").strip().lower()
        hint = (row.get("search_hint") or "").strip() or code
        outfile = os.path.join(out_dir, f"{num}_{code}.png")

        if os.path.exists(outfile):
            log(f"[=] {outfile} exists; skipping")
            written[code] = outfile
            continue

        url = None
        if code in overrides:
            url = overrides[code]
            log(f"[A] override for {code}: {url}")

        if not url:
            q = hint
            if ch_type == "local":
                q = guess_station_title(code)
            title = wp_search_title(q)
            nap()
            if not title and code != hint:
                title = wp_search_title(code)
                nap()
            if title:
                qid = wp_get_wikibase_item(title)
                nap()
                if qid:
                    fname = wd_get_logo_filename(qid)
                    nap()
                    if fname:
                        url = commons_file_url(fname, px)
                        log(f"[B] {code} via {title} / {qid} -> {fname}")

        if not url:
            for term in (hint, code):
                gh = github_tvlogos_search(term)
                nap()
                if gh:
                    url = gh
                    log(f"[C] {code} via GitHub search: {term} -> {gh}")
                    break

        data = download(url) if url else None
        if data:
            try:
                png = normalize_png(data, px)
                with open(outfile, "wb") as fo:
                    fo.write(png)
                log(f"[✓] {num} {code} -> {os.path.basename(outfile)}")
                success += 1
                written[code] = outfile
                continue
            except Exception as exc:
                log(f"[!] normalize failed for {code}: {exc}")

        placeholder_codes = {
            "VALU",
            "RENEW",
            "DEAL",
            "INFO",
            "MALL",
            "SHOP",
            "BOOST",
            "EXTRA",
            "SALE",
            "SCAP1",
            "SCAP2",
            "SCAP3",
            "SCAP4",
            "BINGE",
            "ICTV",
            "YOUTV",
            "MSG4",
            "AMVO",
            "WEST",
            "PRTGS",
            "AUD",
            "AUD01",
            "AUD02",
            "AUD03",
            "AUD04",
            "AUD05",
            "AUD06",
            "AUD07",
            "AUD08",
            "AUD09",
            "AUD10",
            "AUD11",
            "AUD12",
            "AUD13",
            "ES24",
            "TODOC",
            "TONOM",
            "TDV",
            "ENLC",
            "MVSHG",
            "BITV",
            "HERIC",
        }
        try:
            from PIL import ImageDraw, ImageFont

            im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            text = code if code in placeholder_codes else code[:6]
            size = int(px * 0.28)
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
            except Exception:
                font = ImageFont.load_default()
            w, h = draw.textsize(text, font=font)
            draw.rectangle([(0, 0), (px - 1, px - 1)], outline=(180, 180, 180, 255), width=2)
            draw.text(((px - w) // 2, (px - h) // 2), text, font=font, fill=(80, 80, 80, 255))
            im.save(outfile, "PNG")
            log(f"[•] {num} {code} -> placeholder")
            success += 1
            written[code] = outfile
        except Exception as exc:
            log(f"[x] {num} {code} failed: {exc}")
            fail += 1

    log(f"\nDone. Success: {success}, Fail: {fail}. Logos are in {out_dir}")
    log("Tip: set TARGET_PX=96 (or 64/128/256) to control size.")
    return written


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Fetch channel logos into a local folder.")
    parser.add_argument("--channels-csv", default="channels.csv", help="Path to channels.csv")
    parser.add_argument(
        "--overrides-csv",
        default="overrides.csv",
        help="Optional overrides CSV with columns code,direct_image_url",
    )
    parser.add_argument("--output-dir", default="./output", help="Directory for generated PNGs")
    parser.add_argument("--target-px", type=int, default=None, help="Square logo size in pixels")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv or sys.argv[1:])
    fetch_channel_logos(
        channels_csv=args.channels_csv,
        overrides_csv=args.overrides_csv,
        output_dir=args.output_dir,
        target_px=args.target_px,
    )


if __name__ == "__main__":
    main()
