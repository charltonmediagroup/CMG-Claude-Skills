#!/usr/bin/env python3
"""Read column D of the target tab and emit the set of URLs already present.

Usage:
    python sheet_existing_urls.py --sa secrets/gsheets-sa.json \
        --sheet-id <id> --tab "<tab>" --out cache/existing_urls.json
"""
import argparse
import json
import os
import sys

import gspread


def normalize(u):
    return (u or "").strip().rstrip("/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gc = gspread.service_account(filename=args.sa)
    sh = gc.open_by_key(args.sheet_id)
    ws = sh.worksheet(args.tab)
    raw = ws.col_values(4)  # column D
    urls = sorted({normalize(u) for u in raw if u and u.lower().startswith("http")})

    payload = {"sheet_id": args.sheet_id, "tab": args.tab, "count": len(urls), "urls": urls}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"OK existing URLs: {len(urls)} -> {args.out}")


if __name__ == "__main__":
    main()
