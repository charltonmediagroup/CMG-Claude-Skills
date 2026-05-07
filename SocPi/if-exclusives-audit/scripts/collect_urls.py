"""Collect IF & Exclusive article URLs from the publication RSS feeds and
populate column A of the 'IF & Exclusives' tab in the Charlton Media sheet.

Reads:
  - "IF & Exclusives XML" tab, A2:B<n>: per-publication RSS feed URLs
        (col A = "In Focus" feed, col B = "Exclusives" feed)
  - "IF & Exclusives" tab, B1 and C1: date range (MM-DD-YYYY, inclusive)

Writes:
  - "IF & Exclusives" tab, A2:A: deduped URLs whose <pubDate> falls in range,
        sorted by pubDate descending. Header row 1 is preserved.
  - cache/url_collection_log.txt: append-mode warning log.

Failure modes are categorized:
  - FETCH    : feed URL was unreachable / 4xx / 5xx / SSL / timeout
  - PARSE    : feed body wasn't well-formed XML
  - EMPTY    : feed parsed fine but had 0 items in the date window
  - PUBDATE  : individual <item>'s pubDate was unparseable (item skipped,
               rest of the feed kept)

One bad feed never aborts the run. Hard-fails only on:
  - bad CLI args / missing flags
  - gspread auth failure
  - malformed B1/C1 date cells (or start > end)
  - zero URLs collected AND --allow-empty was not passed (exit 4)

CLI:
    python collect_urls.py \\
        --sa secrets/gsheets-sa.json \\
        --sheet-id <sheet-id> \\
        --tab "IF & Exclusives" \\
        --xml-tab "IF & Exclusives XML" \\
        --log cache/url_collection_log.txt \\
        [--timeout 20] [--workers 16] [--allow-empty]
"""

import argparse
import datetime as dt
import gzip
import io
import re
import socket
import ssl
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import error as urlerr
from urllib import request as urlreq


USER_AGENT = ("Mozilla/5.0 (compatible; if-exclusives-audit/1.0; "
              "+https://www.charltonmedia.com)")

# Per-feed timeout overrides for slow / large feeds. Substring-matched against
# the feed URL. The default --timeout (60s) covers most feeds; only the truly
# heavy ones need extra time. Add new entries here when a feed starts timing
# out — they're checked in order.
PER_FEED_TIMEOUT_OVERRIDES = (
    # SBR's in-focus feed is genuinely large (multi-year backlog) and slow to
    # serve over plain HTTP. Bumped from 60s -> 180s.
    ("sbr.com.sg/in-focus-articles.xml", 180),
)


def effective_timeout(url: str, default_timeout: int) -> int:
    """Return the timeout to use for this feed URL, honoring per-feed overrides."""
    for pattern, timeout in PER_FEED_TIMEOUT_OVERRIDES:
        if pattern in url:
            return max(default_timeout, timeout)
    return default_timeout

# Strip leading "Day, " from RSS pubDate strings like "Thu, 04/23/2026 - 1:00 pm".
DAY_PREFIX_RE = re.compile(r"^[A-Za-z]{3,9},\s+")

# Try these formats in order against a pubDate string after stripping the day.
_PUBDATE_FORMATS = (
    "%m/%d/%Y - %I:%M %p",   # "04/23/2026 - 1:00 pm"
    "%m/%d/%Y - %I:%M%p",    # "04/23/2026 - 1:00pm"  (no space before am/pm)
    "%m/%d/%Y - %H:%M",      # "04/23/2026 - 13:00"   (24h, just in case)
    "%m/%d/%Y",              # "04/23/2026"           (date only)
)


def parse_pubdate(raw: str) -> dt.datetime | None:
    """Parse a Charlton-style RSS pubDate.

    Examples that should succeed:
      'Thu, 04/23/2026 - 1:00 pm'
      '04/23/2026 - 1:00pm'
      '04/23/2026'
      'WED, 04/23/2026 - 11:30 AM'

    Returns naive datetime or None on unparseable input. Caller treats None
    as "skip this item, but don't fail the whole feed."
    """
    if not raw:
        return None
    s = raw.strip()
    s = DAY_PREFIX_RE.sub("", s)
    # Lowercase the am/pm token so %p matches regardless of casing.
    s = re.sub(r"\b([AaPp])([Mm])\b",
               lambda m: m.group(0).lower(), s)
    for fmt in _PUBDATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# Substrings in error messages that indicate a TRANSIENT failure worth retrying.
# DNS hiccups, connection refused, SSL handshake races — all typically clear up
# on a second or third attempt within a few seconds. Timeout-class errors
# (plain socket timeout, HTTP 408 / 504 / 522 / 524) are also retried — slow
# origins / Cloudflare gateways frequently succeed on a second attempt.
_TRANSIENT_ERROR_MARKERS = (
    "getaddrinfo failed",                # Windows DNS lookup failure (errno 11001)
    "Name or service not known",          # Linux DNS lookup failure
    "Temporary failure in name resolution",  # Linux/macOS DNS hiccup
    "Connection refused",
    "Connection reset",
    "Network is unreachable",
    "EOF occurred in violation of protocol",  # SSL handshake race
    "HTTP 502", "HTTP 503", "HTTP 504",   # transient server-side errors
    "HTTP 408", "HTTP 429",               # request timeout / rate limited
    "HTTP 522", "HTTP 524",               # Cloudflare origin connection / timeout
    "timeout after",                      # plain socket timeout — retry may hit a healthier worker
)


def _is_transient(err: str | None) -> bool:
    if not err:
        return False
    return any(marker in err for marker in _TRANSIENT_ERROR_MARKERS)


def _fetch_once(url: str, timeout: int) -> tuple[bytes | None, str | None]:
    """One fetch attempt. Returns (body, None) on success, (None, err) on failure."""
    try:
        req = urlreq.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        })
        with urlreq.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower().strip()
            if enc == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError as e:
                    return None, f"gzip decompress: {e}"
            elif enc == "deflate":
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    try:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    except zlib.error as e:
                        return None, f"deflate decompress: {e}"
            return raw, None
    except urlerr.HTTPError as e:
        return None, f"HTTP {e.code}"
    except urlerr.URLError as e:
        return None, f"URL error: {e.reason}"
    except (socket.timeout, TimeoutError):
        return None, f"timeout after {timeout}s"
    except ssl.SSLError as e:
        return None, f"SSL error: {e}"
    except Exception as e:
        return None, f"unexpected: {type(e).__name__}: {e}"


def fetch_feed(url: str, timeout: int,
               max_attempts: int = 3,
               retry_delays: tuple[int, ...] = (2, 5),
               ) -> tuple[bytes | None, str | None]:
    """Fetch one RSS feed with retry on TRANSIENT errors.

    Sends Accept-Encoding: gzip, deflate to reduce transfer size — RSS XML
    typically compresses 3-5x. Decompresses transparently.

    Retries up to `max_attempts - 1` times on errors matching
    `_TRANSIENT_ERROR_MARKERS` (DNS hiccups, 5xx, 429, etc). Does NOT retry
    on hard failures (404, 403, parse errors, plain timeouts). Sleeps
    `retry_delays[i]` seconds between attempts.

    The final error message includes "(after N attempts)" so the log makes
    clear we already tried before giving up.
    """
    if not url or not url.strip():
        return None, "empty URL"
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    last_err: str | None = None
    attempts_made = 0
    for attempt in range(max_attempts):
        attempts_made += 1
        body, err = _fetch_once(url, timeout)
        if body is not None:
            return body, None
        last_err = err
        if not _is_transient(err) or attempt >= max_attempts - 1:
            break
        # Sleep before retry, then loop.
        delay = retry_delays[min(attempt, len(retry_delays) - 1)]
        time.sleep(delay)

    # Only mention retries if we actually retried (kept honest so the operator
    # can tell whether 60s × 3 was already tried or just 60s × 1).
    suffix = f" (after {attempts_made} attempts)" if attempts_made > 1 else ""
    return None, f"{last_err}{suffix}"


def extract_items(xml_bytes: bytes) -> tuple[list[dict], str | None]:
    """Return ([{link, pubdate_raw, title}, ...], None) or ([], err)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return [], f"not well-formed: {e}"
    out: list[dict] = []
    for item in root.iter("item"):
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        title_el = item.find("title")
        link = (link_el.text or "").strip() if link_el is not None else ""
        if not link:
            continue
        out.append({
            "link": link,
            "pubdate_raw": (pub_el.text or "").strip() if pub_el is not None else "",
            "title": (title_el.text or "").strip() if title_el is not None else "",
        })
    return out, None


def filter_by_date(items: list[dict],
                   start: dt.date, end: dt.date,
                   ) -> tuple[list[dict], int]:
    """Keep items whose pubDate (date-only) falls in [start, end]. Returns
    (kept_items, count_of_unparseable_pubdates_skipped).
    """
    kept = []
    bad_pubdate = 0
    for it in items:
        d = parse_pubdate(it["pubdate_raw"])
        if d is None:
            bad_pubdate += 1
            continue
        if start <= d.date() <= end:
            it["pubdate"] = d
            kept.append(it)
    return kept, bad_pubdate


def read_xml_tab(ws_xml) -> list[tuple[str, str, str]]:
    """Return [(pub_label, in_focus_url, exclusive_url), ...] from rows 2-50,
    cols A & B. pub_label is derived from the URL host as a stable identifier.
    """
    rows = ws_xml.get("A2:B50") or []
    out = []
    for row in rows:
        if_url = (row[0] if len(row) > 0 else "").strip()
        ex_url = (row[1] if len(row) > 1 else "").strip()
        if not (if_url or ex_url):
            continue
        # Pub label: host of first non-empty URL, normalized.
        sample = if_url or ex_url
        m = re.search(r"https?://([^/]+)", sample if "://" in sample else "https://" + sample)
        pub = m.group(1).lower().lstrip("www.") if m else sample
        out.append((pub, if_url, ex_url))
    return out


def read_date_range(ws_main) -> tuple[dt.date, dt.date]:
    """Read B1:C1 from the main tab and parse as MM-DD-YYYY inclusive range.

    Hard-fails (SystemExit 2) on missing/malformed cells or start > end.
    """
    cells = ws_main.get("B1:C1")
    if not cells or not cells[0] or len(cells[0]) < 2:
        print("ERROR: B1 and C1 must hold start and end dates (MM-DD-YYYY)",
              file=sys.stderr)
        sys.exit(2)
    raw_start, raw_end = cells[0][0].strip(), cells[0][1].strip()
    try:
        start = dt.datetime.strptime(raw_start, "%m-%d-%Y").date()
        end = dt.datetime.strptime(raw_end, "%m-%d-%Y").date()
    except ValueError as e:
        print(f"ERROR: B1/C1 not in MM-DD-YYYY format: {e}", file=sys.stderr)
        sys.exit(2)
    if start > end:
        print(f"ERROR: B1 ({start}) is after C1 ({end})", file=sys.stderr)
        sys.exit(2)
    return start, end


def wipe_and_write_column_a(ws_main, urls: list[str]) -> None:
    """Clear A2:H1000 then write the new URL list starting at A2.

    Wiping the WHOLE data area (A:H, not just column A) prevents stale data
    from a previous audit run from sitting next to fresh URLs. Specifically:

    - write_to_sheet.py from a prior run may have left feed-report cells in
      B-E of rows below where the previous article list ended.
    - If the new URL list is longer/shorter than the previous one, those
      stale rows would otherwise overlap with the new article URLs in
      column A and look like data corruption.

    Header row 1 (Urls / date cells / column headers in D-H) is preserved.
    The new article URLs go in A2:A(N+1); write_to_sheet.py later refills
    D-H for those rows and appends the fresh feed report below.
    """
    ws_main.batch_clear(["A2:H1000"])
    if urls:
        body = [[u] for u in urls]
        ws_main.update(values=body, range_name="A2",
                       value_input_option="USER_ENTERED")


def write_log(path: Path, header: str, warnings: list[tuple]) -> None:
    """Append the run's warnings to the log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(header + "\n")
        for cat, pub, kind, url, msg in warnings:
            f.write(f"WARN {cat:7s} {pub:35s} {kind:9s} {url[:80]:80s} {msg}\n")
        f.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tab", default="IF & Exclusives")
    ap.add_argument("--xml-tab", default="IF & Exclusives XML")
    ap.add_argument("--log", default="cache/url_collection_log.txt")
    ap.add_argument("--timeout", type=int, default=60,
                    help="Per-feed HTTP timeout in seconds (default 60). "
                         "Bumped from 20 because some publication feeds are large.")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--allow-empty", action="store_true",
                    help="Don't hard-fail when 0 URLs result from the date window. "
                         "By default the script exits 4 to prevent silent wipe.")
    args = ap.parse_args()

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
    ws_main = sh.worksheet(args.tab)
    ws_xml = sh.worksheet(args.xml_tab)

    start, end = read_date_range(ws_main)
    print(f"date range: {start} .. {end} (inclusive)", file=sys.stderr)

    feeds = read_xml_tab(ws_xml)
    print(f"feeds: {len(feeds)} publications", file=sys.stderr)

    # Build job list: (pub, kind, url) for each non-empty feed URL.
    jobs: list[tuple[str, str, str]] = []
    for pub, if_url, ex_url in feeds:
        if if_url:
            jobs.append((pub, "IF", if_url))
        if ex_url:
            jobs.append((pub, "EXCLUSIVE", ex_url))
    print(f"jobs: {len(jobs)} feed fetches", file=sys.stderr)

    # Parallel fetch with per-feed timeout overrides.
    def _do(job):
        pub, kind, url = job
        timeout = effective_timeout(url, args.timeout)
        body, err = fetch_feed(url, timeout)
        return (pub, kind, url, body, err)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(_do, jobs))

    # Per-feed parse + date filter; aggregate into by_url with most-recent-wins.
    by_url: dict[str, dict] = {}
    warnings: list[tuple] = []
    pre_dedup_total = 0
    for pub, kind, url, body, err in results:
        if err:
            warnings.append(("FETCH", pub, kind, url, err))
            continue
        items, perr = extract_items(body or b"")
        if perr:
            warnings.append(("PARSE", pub, kind, url, perr))
            continue
        kept, bad_pubdate = filter_by_date(items, start, end)
        if bad_pubdate:
            warnings.append(("PUBDATE", pub, kind, url,
                             f"{bad_pubdate} item(s) had unparseable pubDate"))
        if not kept:
            warnings.append(("EMPTY", pub, kind, url,
                             f"0 items in {start}..{end}"))
            continue
        pre_dedup_total += len(kept)
        for it in kept:
            existing = by_url.get(it["link"])
            if existing is None or it["pubdate"] > existing["pubdate"]:
                by_url[it["link"]] = {**it, "pub": pub}

    ordered = [u for u, _ in sorted(by_url.items(),
                                    key=lambda kv: kv[1]["pubdate"],
                                    reverse=True)]

    # Run header for the log file.
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (f"=== run {now_iso}  range {start}..{end}  "
              f"jobs={len(jobs)} kept={pre_dedup_total} "
              f"deduped={len(ordered)} ===")
    print(header, file=sys.stderr)

    # Print all warnings to stderr too (orchestrator surfaces them).
    for cat, pub, kind, url, msg in warnings:
        print(f"  WARN {cat:7s} {pub:30s} {kind:9s} {url[:60]:60s} {msg}",
              file=sys.stderr)

    log_path = Path(args.log)
    write_log(log_path, header, warnings)

    if not ordered:
        if args.allow_empty:
            print("0 URLs after filter; --allow-empty given, wiping column A "
                  "and continuing", file=sys.stderr)
            wipe_and_write_column_a(ws_main, [])
            return
        print("ERROR: 0 URLs collected from the configured date window. "
              "Refusing to wipe column A. Re-run with --allow-empty to override.",
              file=sys.stderr)
        sys.exit(4)

    wipe_and_write_column_a(ws_main, ordered)
    print(f"wrote {len(ordered)} URLs to A2:A{len(ordered)+1} on '{args.tab}'",
          file=sys.stderr)
    # Show a sample so the operator can sanity-check.
    for u in ordered[:3]:
        print(f"  - {u}", file=sys.stderr)


if __name__ == "__main__":
    main()
