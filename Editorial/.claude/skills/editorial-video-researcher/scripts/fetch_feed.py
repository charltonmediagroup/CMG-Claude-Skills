#!/usr/bin/env python3
"""Download a publication's top-read XML feed and emit items as JSON.

Usage:
    python fetch_feed.py --pub SBR --out cache/feeds/SBR.json [--config ../config.yaml]

Output JSON shape:
    {"pub": "SBR", "name": "Singapore Business Review", "feed": "<url>",
     "items": [{"title": "...", "url": "...", "pub_date": "..."}, ...]}
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

import yaml


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse(raw):
    root = ET.fromstring(raw)
    items = root.findall(".//item")
    out = []
    for it in items:
        out.append({
            "title": (it.findtext("title") or "").strip(),
            "url": (it.findtext("link") or "").strip(),
            "pub_date": (it.findtext("pubDate") or "").strip(),
        })
    return out


def filter_excluded(items, excluded_segments):
    """Drop items whose URL contains any of the excluded path segments.

    Returns (kept_items, dropped_items). Each dropped item is annotated with
    the matching segment so the caller can log it.
    """
    if not excluded_segments:
        return list(items), []
    kept, dropped = [], []
    for it in items:
        url = it.get("url", "")
        match = next((seg for seg in excluded_segments if seg in url), None)
        if match:
            entry = dict(it)
            entry["excluded_by"] = match
            dropped.append(entry)
        else:
            kept.append(it)
    return kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", required=True, help="publication abbreviation, e.g. SBR")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    pubs = cfg.get("publications", {})
    if args.pub not in pubs:
        sys.stderr.write(f"unknown pub {args.pub!r}; known: {sorted(pubs)}\n")
        sys.exit(2)
    entry = pubs[args.pub]

    headers = {"User-Agent": cfg.get("http_headers", {}).get("User-Agent", "Mozilla/5.0")}
    try:
        raw = fetch(entry["feed"], headers)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        sys.stderr.write(f"FETCH FAIL {entry['feed']}: {e}\n")
        sys.exit(3)

    try:
        all_items = parse(raw)
    except ET.ParseError as e:
        sys.stderr.write(f"PARSE FAIL {entry['feed']}: {e}\n")
        sys.exit(4)

    excluded = cfg.get("excluded_path_segments", []) or []
    items, dropped = filter_excluded(all_items, excluded)

    payload = {
        "pub": args.pub,
        "name": entry["name"],
        "feed": entry["feed"],
        "items": items,
        "excluded": dropped,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    msg = f"OK {args.pub}: {len(items)} items -> {args.out}"
    if dropped:
        msg += f"  ({len(dropped)} excluded by path: " \
               + ", ".join(sorted({d['excluded_by'] for d in dropped})) + ")"
    print(msg)


if __name__ == "__main__":
    main()
