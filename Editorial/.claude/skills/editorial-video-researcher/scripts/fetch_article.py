#!/usr/bin/env python3
"""Fetch a Charlton Media article page and extract Title/Deck/Body from its JSON-LD.

Usage:
    python fetch_article.py --url <url> --out cache/articles/<slug>.json [--config ../config.yaml]

Output JSON shape:
    {"url": "...", "title": "...", "deck": "...", "body": "...",
     "paragraphs": ["...", ...]}

The body field is paragraphs joined by "\\n\\n" (matches the convention in
column G of [2026] Discussion Topic — actually used for column C summary
generation, not the literal body).
"""
import argparse
import gzip
import io
import json
import os
import re
import sys
import urllib.request
import urllib.error

import yaml


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_html(url, headers, timeout=45):
    headers = dict(headers)
    headers.setdefault("Accept-Encoding", "gzip, deflate")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
        return body.decode("utf-8", errors="replace")


def extract_jsonld_newsarticle(html):
    """Return the parsed @type=NewsArticle dict, or None."""
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                          html, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph") if isinstance(data, dict) else None
        candidates = graph if isinstance(graph, list) else [data]
        for node in candidates:
            if isinstance(node, dict) and node.get("@type") == "NewsArticle":
                return node
    return None


def split_deck_body(description):
    """First line = deck; remaining lines = body paragraphs."""
    parts = [p.strip() for p in (description or "").split("\n")]
    parts = [p for p in parts if p]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    headers = cfg.get("http_headers", {})

    try:
        html = fetch_html(args.url, headers)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        sys.stderr.write(f"FETCH FAIL {args.url}: {e}\n")
        sys.exit(3)

    node = extract_jsonld_newsarticle(html)
    if not node:
        sys.stderr.write(f"NO JSON-LD NewsArticle on {args.url}\n")
        sys.exit(4)

    title = (node.get("headline") or "").strip()
    deck, paragraphs = split_deck_body(node.get("description") or "")

    payload = {
        "url": args.url,
        "title": title,
        "deck": deck,
        "body": "\n\n".join(paragraphs),
        "paragraphs": paragraphs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"OK {args.url} -> {args.out}  (title={len(title)}c, deck={len(deck)}c, body={len(payload['body'])}c)")


if __name__ == "__main__":
    main()
