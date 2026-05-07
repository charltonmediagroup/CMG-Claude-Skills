"""Write per-platform post permalinks (or SCHEDULED markers) back to the sheet.

For each article URL in column A of the 'IF & Exclusives' tab:

  D = Facebook URL    E = Instagram URL    F = LinkedIn URL    G = X URL
  H = Status

Cell content per platform:
  - Posted match    → permalink URL (e.g. https://facebook.com/...)
  - Scheduled match → "SCHEDULED 2026-05-02 10:00"
  - Neither         → empty

Status hierarchy: DUPLICATE ISSUE > COMPLETE > PARTIAL > SCHEDULED > MISSING.

DEFAULT IS COMMIT (auto-write). Pass --dry-run to preview without writing.
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import re


DROP_PARAMS = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|igshid|si)$",
                         re.IGNORECASE)


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    if not p.scheme:
        return url.strip().lower()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
          if not DROP_PARAMS.match(k)]
    qs.sort()
    return urlunparse(("https", host, path, "", urlencode(qs), ""))


PLATFORM_COLS = [("facebook", "Facebook URL", "D"),
                 ("instagram", "Instagram URL", "E"),
                 ("linkedin", "LinkedIn URL", "F"),
                 ("twitter", "X URL", "G")]
STATUS_HEADER = "Status"
STATUS_COL_LETTER = "H"

# Pattern to parse one warning line from cache/url_collection_log.txt:
#   WARN FETCH    asianbankingfinance.net  IF        https://...  HTTP 503
URL_LOG_LINE_RE = re.compile(
    r"^WARN\s+(?P<cat>FETCH|PARSE|EMPTY|PUBDATE)\s+"
    r"(?P<pub>\S+)\s+(?P<kind>\S+)\s+(?P<url>\S+)\s+(?P<detail>.+?)\s*$"
)
# Header line: === run <iso>  range <start>..<end>  jobs=N kept=N deduped=N ===
URL_LOG_HEADER_RE = re.compile(r"range (\S+)\.\.(\S+)\s+jobs=(\d+)\s+kept=(\d+)\s+deduped=(\d+)")


def read_feed_warnings(log_path: Path) -> tuple[str, list[tuple]]:
    """Parse the most recent block of cache/url_collection_log.txt.

    Returns (date_range_label, [(category, pub, kind, url, detail), ...]).
    Only FETCH, PARSE, and EMPTY warnings are returned (these answer "which
    XML failed" and "which XML had no articles in the date window"). PUBDATE
    is item-level noise and isn't surfaced in the sheet.
    """
    if not log_path.exists():
        return "", []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", []
    blocks = [b for b in text.split("=== run ") if b.strip()]
    if not blocks:
        return "", []
    last = "=== run " + blocks[-1]
    lines = last.split("\n")
    header = lines[0]
    m = URL_LOG_HEADER_RE.search(header)
    label = f"{m.group(1)} to {m.group(2)}" if m else "unknown date range"
    warnings: list[tuple] = []
    for line in lines[1:]:
        wm = URL_LOG_LINE_RE.match(line)
        if not wm:
            continue
        cat = wm.group("cat")
        if cat == "PUBDATE":
            continue
        warnings.append((cat, wm.group("pub"), wm.group("kind"),
                         wm.group("url"), wm.group("detail").strip()))
    return label, warnings


def build_feed_report_updates(start_row: int, label: str,
                              warnings: list[tuple]) -> list[tuple[int, int, str]]:
    """Build (row, col, value) updates for the XML feed health section that
    sits below the article rows. Layout, starting at start_row:

        row N  : A="XML Feed Issues — <date range>"
        row N+1: A="Publication"  B="Type"  C="Feed URL"  D="Issue"  E="Details"
        row N+2: one row per warning (FETCH or PARSE or EMPTY)
    """
    if not warnings:
        return []
    updates: list[tuple[int, int, str]] = []
    title = f"XML Feed Issues — {label} (Step 1a)"
    updates.append((start_row, 1, title))
    headers = ["Publication", "Type", "Feed URL", "Issue", "Details"]
    for i, h in enumerate(headers):
        updates.append((start_row + 1, 1 + i, h))
    # Sort: FETCH first, then PARSE, then EMPTY (most-actionable first).
    cat_order = {"FETCH": 0, "PARSE": 1, "EMPTY": 2}
    for i, (cat, pub, kind, url, detail) in enumerate(
            sorted(warnings, key=lambda w: (cat_order.get(w[0], 9), w[1], w[2]))):
        r = start_row + 2 + i
        updates.append((r, 1, pub))
        updates.append((r, 2, kind))
        updates.append((r, 3, url))
        updates.append((r, 4, cat))
        updates.append((r, 5, detail))
    return updates


def normalize_scheduled_at(raw: str) -> str:
    """Coerce SocialPilot's various scheduled-at strings into 'YYYY-MM-DD HH:MM'."""
    if not raw:
        return ""
    s = raw.strip()
    # Common shape from postTimeFormat: '2026-04-29 11:15'.
    if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", s):
        return s[:16]
    # 'Apr 13, 2026 09:13 AM' style — convert to ISO-ish.
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M")
        except Exception:
            continue
    return s  # fallback: pass through


def _hyperlink(url: str, label: str) -> str:
    """Wrap (url, label) in a Google Sheets HYPERLINK formula.

    Falls back to the bare URL when label is empty so the cell is still
    clickable. Escapes embedded quotes per Sheets formula rules.
    """
    if not label:
        return url
    safe_label = label.replace('"', '""').strip()
    safe_url = url.replace('"', '""')
    return f'=HYPERLINK("{safe_url}","{safe_label}")'


def best_platform_cell(article: dict, platform: str) -> str:
    """Posted permalink wins; else SCHEDULED <ts>; else empty.

    Posted cells are wrapped in =HYPERLINK(url, headline) so the team sees
    the actual post headline as clickable text instead of a raw URL.
    """
    posted_list = (article.get("posted_matches") or {}).get(platform) or []
    fuzzy_list = (article.get("fuzzy_matches") or {}).get(platform) or []
    fuzzy_posted = [m for m in fuzzy_list if m.get("kind") != "scheduled"]
    for src in (posted_list, fuzzy_posted):
        for post in src:
            link = post.get("permalink") or ""
            if link:
                headline = (post.get("headline") or "").strip()
                return _hyperlink(link, headline)
    scheduled_list = (article.get("scheduled_matches") or {}).get(platform) or []
    fuzzy_scheduled = [m for m in fuzzy_list if m.get("kind") == "scheduled"]
    for src in (scheduled_list, fuzzy_scheduled):
        for post in src:
            ts = normalize_scheduled_at(post.get("scheduled_at") or "")
            return f"SCHEDULED {ts}".strip()
    return ""


def derive_status(article: dict) -> tuple[str, bool]:
    posted = article.get("posted_matches") or {}
    scheduled = article.get("scheduled_matches") or {}
    fuzzy = article.get("fuzzy_matches") or {}
    posted_set, sched_set = [], []
    duplicate = False
    for key, _, _ in PLATFORM_COLS:
        fuzzy_posted = [m for m in (fuzzy.get(key) or []) if m.get("kind") != "scheduled"]
        fuzzy_scheduled = [m for m in (fuzzy.get(key) or []) if m.get("kind") == "scheduled"]
        all_posted = list(posted.get(key) or []) + fuzzy_posted
        all_sched = list(scheduled.get(key) or []) + fuzzy_scheduled
        if all_posted:
            posted_set.append(key)
            if len(all_posted) > 1:
                duplicate = True
        elif all_sched:
            sched_set.append(key)
    if duplicate:
        return "DUPLICATE ISSUE", True
    if len(posted_set) == 4:
        return "COMPLETE", False
    if posted_set:
        return "PARTIAL", False
    if sched_set:
        return "SCHEDULED", False
    return "MISSING", False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("matches")
    ap.add_argument("--sa", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tab", default="IF & Exclusives")
    ap.add_argument("--commit", action="store_true",
                    help="(legacy) commit writes; default behavior now")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview without writing to the sheet")
    ap.add_argument("--url-log", default="cache/url_collection_log.txt",
                    help="Path to url_collection_log.txt; warnings from the "
                         "most recent block are appended below the article "
                         "rows as an 'XML Feed Issues' section.")
    ap.add_argument("--skip-feed-report", action="store_true",
                    help="Don't render the XML feed health section. Used by "
                         "the /if-exclusives-audit-quick skill (which skips "
                         "RSS collection entirely, so any log block in "
                         "url_collection_log.txt would be stale).")
    args = ap.parse_args()
    # Default to commit; --dry-run opts out.
    args.commit = not args.dry_run

    articles = json.loads(Path(args.matches).read_text(encoding="utf-8"))
    by_norm = {}
    for a in articles:
        n = a.get("norm_url") or normalize_url(a["url"])
        a["norm_url"] = n
        by_norm[n] = a

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("ERROR: pip install gspread google-auth", file=sys.stderr)
        sys.exit(2)

    creds = Credentials.from_service_account_file(
        args.sa,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(args.sheet_id)
    ws = sh.worksheet(args.tab)

    col_a = ws.col_values(1)
    header_row = ws.row_values(1)
    while len(header_row) < 8:
        header_row.append("")

    desired_headers = {3: PLATFORM_COLS[0][1],   # D
                       4: PLATFORM_COLS[1][1],   # E
                       5: PLATFORM_COLS[2][1],   # F
                       6: PLATFORM_COLS[3][1],   # G
                       7: STATUS_HEADER}         # H
    header_updates = []
    for col_idx, want in desired_headers.items():
        if header_row[col_idx] != want:
            header_updates.append((1, col_idx + 1, want))

    row_updates = []
    summary = {"matched": 0, "no_match_in_sheet": 0,
               "rows_with_scheduled": 0, "rows_with_posted": 0}

    for row_idx, url in enumerate(col_a[1:], start=2):
        if not url or not url.strip():
            continue
        article = by_norm.get(normalize_url(url.strip()))
        if not article:
            summary["no_match_in_sheet"] += 1
            # Still clear status to keep cells in sync.
            for _, _, col_letter in PLATFORM_COLS:
                ci = ord(col_letter) - ord("A") + 1
                row_updates.append((row_idx, ci, ""))
            row_updates.append((row_idx, 8, ""))
            continue
        summary["matched"] += 1

        any_posted = any(article.get("posted_matches", {}).get(p) for p, _, _ in PLATFORM_COLS)
        any_scheduled = any(article.get("scheduled_matches", {}).get(p) for p, _, _ in PLATFORM_COLS)
        if any_posted:
            summary["rows_with_posted"] += 1
        if any_scheduled and not any_posted:
            summary["rows_with_scheduled"] += 1

        for plat_key, _, col_letter in PLATFORM_COLS:
            value = best_platform_cell(article, plat_key)
            ci = ord(col_letter) - ord("A") + 1
            row_updates.append((row_idx, ci, value))
        status, _ = derive_status(article)
        row_updates.append((row_idx, 8, status))

    # Append the XML Feed Issues section in rows below the article rows.
    # When --skip-feed-report is set (quick audit), don't render the full
    # warnings table — it would be stale (from a previous collect_urls run).
    # Drop a single explainer row instead so the operator knows feed status
    # wasn't collected in this audit.
    last_article_row = max((r for r, _, _ in row_updates), default=1)
    if args.skip_feed_report:
        feed_warnings = []
        feed_report_updates = [(
            last_article_row + 2, 1,
            "(Quick audit — RSS feed collection skipped. Column A is from a "
            "prior run; feed health is not refreshed in this audit. Run "
            "/if-exclusives-audit for fresh feed status.)"
        )]
    else:
        feed_label, feed_warnings = read_feed_warnings(Path(args.url_log))
        feed_report_updates = build_feed_report_updates(
            last_article_row + 2, feed_label, feed_warnings)
    row_updates.extend(feed_report_updates)

    print(f"Sheet: {sh.title}  Tab: {ws.title}", file=sys.stderr)
    print(f"Articles in sheet: {sum(1 for u in col_a[1:] if u and u.strip())}", file=sys.stderr)
    print(f"Matched: {summary['matched']}, no match in matches.json: {summary['no_match_in_sheet']}",
          file=sys.stderr)
    print(f"Rows with at least 1 posted: {summary['rows_with_posted']}", file=sys.stderr)
    print(f"Rows scheduled-only (no posts): {summary['rows_with_scheduled']}", file=sys.stderr)
    print(f"Header updates: {len(header_updates)}", file=sys.stderr)
    print(f"Cell updates: {len(row_updates)} "
          f"(of which {len(feed_report_updates)} are XML feed report rows: "
          f"{len(feed_warnings)} warnings)", file=sys.stderr)
    print(f"Mode: {'COMMIT' if args.commit else 'DRY-RUN (no writes)'}", file=sys.stderr)

    if not args.commit:
        print("\nPreview (first 6 rows):", file=sys.stderr)
        seen_rows = []
        for ri, _, _ in row_updates:
            if ri not in seen_rows:
                seen_rows.append(ri)
                if len(seen_rows) > 6:
                    break
        for ri in seen_rows:
            row_vals = {ci: val for r, ci, val in row_updates if r == ri}
            url_short = (col_a[ri-1] or "")[:60]
            print(f"  row {ri}  {url_short}", file=sys.stderr)
            for col_letter, label in zip("DEFGH", ["FB", "IG", "LI", "X", "Status"]):
                ci = ord(col_letter) - ord("A") + 1
                v = (row_vals.get(ci) or "")[:80]
                print(f"    {col_letter} ({label:6s}) = {v}", file=sys.stderr)
        print("\nRe-run with --commit to write.", file=sys.stderr)
        return

    import gspread.utils

    # Wipe any stale feed-report rows from a previous run before the new
    # report writes fresh content below the article rows. The article rows
    # themselves are managed by collect_urls.py + the row_updates loop above,
    # so we only clear from (last_article_row + 1) onward.
    try:
        ws.batch_clear([f"A{last_article_row + 1}:H1000"])
    except Exception as e:
        print(f"  WARN: could not clear stale rows below articles ({e})",
              file=sys.stderr)

    # Clear any plain-text format on D-H so =HYPERLINK() formulas evaluate
    # instead of showing as raw text. Without this step the cells display the
    # literal formula string. Done before the batch write so first-time setup
    # on a sheet with text-formatted columns self-heals.
    last_row = max((r for r, _, _ in row_updates), default=1)
    try:
        sh.batch_update({
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,           # row 2 (skip header)
                        "endRowIndex": last_row,
                        "startColumnIndex": 3,        # column D
                        "endColumnIndex": 8,          # through column H (exclusive)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": ""}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            }]
        })
    except Exception as e:
        print(f"  WARN: could not clear cell format ({e}); "
              "HYPERLINK formulas may render as text", file=sys.stderr)

    batch = []
    for r, c, v in header_updates + row_updates:
        a1 = gspread.utils.rowcol_to_a1(r, c)
        batch.append({"range": a1, "values": [[v]]})
    if not batch:
        print("Nothing to write.", file=sys.stderr)
        return
    ws.batch_update(batch, value_input_option="USER_ENTERED")
    print(f"Wrote {len(batch)} cells.", file=sys.stderr)


if __name__ == "__main__":
    main()
