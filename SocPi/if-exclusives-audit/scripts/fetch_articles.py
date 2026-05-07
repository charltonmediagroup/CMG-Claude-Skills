"""Fetch articles from the source sheet → articles.json.

Two modes:

1. **Direct via gspread** (preferred — single round-trip, no Drive MCP):
       python fetch_articles.py --sa secrets/gsheets-sa.json \\
           --sheet-id 1Dsj... --tab "IF & Exclusives" --out cache/articles.json

2. **CSV fallback** (legacy — for when no SA file is available):
       python fetch_articles.py cache/sheet.csv --out cache/articles.json
       python fetch_articles.py - --out cache/articles.json   # CSV from stdin

   The CSV is a multi-tab Drive export; we pick the section whose header
   starts with 'Urls,'.
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


def split_tabs(csv_text: str) -> list[list[str]]:
    """Split a multi-tab CSV export into per-tab line groups."""
    lines = csv_text.splitlines()
    tabs: list[list[str]] = []
    current: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if current and blank_run >= 1:
                tabs.append(current)
                current = []
                blank_run = 0
            continue
        blank_run = 0
        current.append(line)
    if current:
        tabs.append(current)
    return tabs


def select_articles_tab(tabs: list[list[str]]) -> list[str]:
    for tab in tabs:
        if not tab:
            continue
        header = tab[0].strip().lower()
        if header.startswith("urls,") or header == "urls":
            return tab
    if len(tabs) == 1:
        return tabs[0]
    raise SystemExit("No tab with 'Urls' header found in CSV export.")


def article_from_url(url: str) -> dict | None:
    url = url.strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    publication = parsed.netloc.lower().lstrip("www.")
    path = parsed.path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    title_guess = slug.replace("-", " ").strip().title() if slug else url
    return {
        "url": url,
        "publication": publication,
        "slug": slug,
        "title_guess": title_guess,
        "path": path,
    }


def parse_articles_from_rows(urls: list[str]) -> list[dict]:
    articles: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for url in urls:
        a = article_from_url(url)
        if not a:
            continue
        key = (a["publication"], a["url"].lower())
        if key in seen:
            continue
        seen.add(key)
        articles.append(a)
    return articles


def parse_csv(csv_text: str) -> list[dict]:
    tabs = split_tabs(csv_text)
    tab = select_articles_tab(tabs)
    reader = csv.reader(io.StringIO("\n".join(tab)))
    rows = list(reader)
    if not rows:
        return []
    header = rows[0]
    if not header or header[0].strip().lower() != "urls":
        raise SystemExit(f"Unexpected header row: {header!r}")
    urls = [row[0] for row in rows[1:] if row]
    return parse_articles_from_rows(urls)


def fetch_via_gspread(sa_path: str, sheet_id: str, tab_name: str) -> list[dict]:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise SystemExit("ERROR: pip install gspread google-auth")
    creds = Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)
    col_a = ws.col_values(1)  # entire column A in one API call
    # Skip header row.
    return parse_articles_from_rows(col_a[1:] if col_a else [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?",
                    help="CSV path or '-' for stdin (legacy mode)")
    ap.add_argument("--sa", help="Service-account key path (gspread mode)")
    ap.add_argument("--sheet-id", help="Google Sheet ID (gspread mode)")
    ap.add_argument("--tab", default="IF & Exclusives",
                    help="Worksheet/tab name (gspread mode)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Prefer gspread mode if SA + sheet-id supplied.
    if args.sa and args.sheet_id:
        articles = fetch_via_gspread(args.sa, args.sheet_id, args.tab)
        print(f"fetched {len(articles)} articles via gspread", file=sys.stderr)
    elif args.csv_path:
        if args.csv_path == "-":
            csv_text = sys.stdin.read()
        else:
            csv_text = Path(args.csv_path).read_text(encoding="utf-8-sig")
        articles = parse_csv(csv_text)
    else:
        ap.error("provide either --sa+--sheet-id, or a CSV path")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(articles, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"Wrote {len(articles)} articles to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
