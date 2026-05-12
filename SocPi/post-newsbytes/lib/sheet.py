"""Read one row from the Weekly NewsBytes sheet.

Column layout (1-indexed):
  A — soundbyte tracking link (ignored here)
  B — date + time, e.g. "May 11, 2026 (3PM)"
  C — article title; cell is hyperlinked to the Google Drive folder/Doc
  D — canonical article URL

We use gspread for plain values and a raw values-with-formulas read to
recover the column-C hyperlink (gspread's get_all_values() returns the
display text, not the link target).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from lib import auth


def read_row(secrets: dict, row: int) -> dict:
    sh = auth.open_sheet(secrets)
    ws = sh.worksheet(secrets["tab"])
    if row < 2:
        raise SystemExit(f"row {row} is the header (or above) — pick row 2 or later")
    values = ws.row_values(row)  # padded with '' for empty trailing cells
    while len(values) < 4:
        values.append("")
    col_b = values[1].strip()
    col_c = values[2].strip()
    col_d = values[3].strip()
    if not col_d:
        raise SystemExit(f"row {row} has no URL in column D — refusing to post")
    doc_url = _extract_hyperlink(ws, row, col_letter="C") or _maybe_url(col_c)
    if not doc_url:
        raise SystemExit(f"row {row} column C is not hyperlinked and contains no URL — refusing to post")
    post_at_local, post_at_utc, mode = _parse_post_time(col_b, secrets["timezone"])
    return {
        "row": row,
        "headline": col_c,
        "doc_url": doc_url,
        "article_url": col_d,
        "raw_date": col_b,
        "post_at_local": post_at_local,
        "post_at_utc": post_at_utc,
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# Column-C hyperlink extraction. gspread doesn't expose the hyperlink
# embedded in a cell via =HYPERLINK() OR via the rich-text "link" annotation
# directly through row_values(), so we go through the underlying API call.
# ---------------------------------------------------------------------------

_HYPERLINK_RE = re.compile(r'=HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)


def _extract_hyperlink(ws, row: int, col_letter: str) -> str | None:
    cell = f"{col_letter}{row}"
    # 1. Try =HYPERLINK() formula via FORMULA value-render.
    try:
        result = ws.get(cell, value_render_option="FORMULA")
    except Exception:
        result = None
    if result and result[0] and result[0][0]:
        m = _HYPERLINK_RE.search(result[0][0])
        if m:
            return m.group(1)
    # 2. Try the rich-text/textFormatRuns hyperlink annotation.
    try:
        api = ws.spreadsheet.values_get  # noqa: F841 — keep gspread version-tolerant
        # gspread itself doesn't expose this, so go through the lower-level
        # service. We pull a single cell with includeGridData to get textFormatRuns.
        spreadsheet_id = ws.spreadsheet.id
        sheet_id = ws.id
        from googleapiclient.discovery import build
        from lib import auth as auth_mod
        creds = auth_mod.google_credentials()
        sheets_api = build("sheets", "v4", credentials=creds, cache_discovery=False)
        rng = f"{ws.title}!{cell}"
        resp = sheets_api.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=[rng],
            includeGridData=True,
            fields="sheets/data/rowData/values(hyperlink,textFormatRuns/format/link/uri,userEnteredValue)"
        ).execute()
        sheets_section = resp.get("sheets", [])
        if sheets_section:
            data = sheets_section[0].get("data", [])
            if data:
                rows = data[0].get("rowData", [])
                if rows:
                    cell_values = rows[0].get("values", [])
                    if cell_values:
                        v = cell_values[0]
                        if v.get("hyperlink"):
                            return v["hyperlink"]
                        runs = v.get("textFormatRuns") or []
                        for run in runs:
                            link = run.get("format", {}).get("link", {}).get("uri")
                            if link:
                                return link
    except Exception:
        pass
    return None


_BARE_URL_RE = re.compile(r"https?://\S+")


def _maybe_url(text: str) -> str | None:
    m = _BARE_URL_RE.search(text or "")
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Date parsing. Inputs we've seen:
#   "May 11, 2026 (3PM)"
#   "April 22 (12PM)"   — year missing, infer from current year
#   "May 13, 2026 (12PM)"
# Output: ISO 8601 strings + mode.
# ---------------------------------------------------------------------------

_PAREN_TIME_RE = re.compile(r"\(([^)]+)\)")


def _parse_post_time(raw: str, tz_name: str) -> tuple[str, str, str]:
    if not raw:
        return "", "", "draft"
    cleaned = raw.replace(" ", " ").strip()
    paren = _PAREN_TIME_RE.search(cleaned)
    time_part = paren.group(1).strip() if paren else ""
    date_part = _PAREN_TIME_RE.sub("", cleaned).strip().rstrip(",")
    candidate = f"{date_part} {time_part}".strip()
    try:
        dt: Any = date_parser.parse(candidate, default=datetime(datetime.now().year, 1, 1))
    except (ValueError, OverflowError):
        return "", "", "draft"
    tz = ZoneInfo(tz_name)
    dt_local = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    dt_utc = dt_local.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    mode = "schedule" if dt_utc > now_utc else "draft"
    return dt_local.isoformat(), dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), mode
