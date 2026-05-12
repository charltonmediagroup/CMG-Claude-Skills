"""Writers for the ad-hoc Companies + POC tabs.

Both writers:
- Open the ad-hoc sheet (auth.open_adhoc_sheet)
- Bootstrap the header row if the tab is empty (so the user doesn't have to
  set columns by hand on a brand-new sheet)
- Re-read the destination tab right before appending so they're idempotent
  against duplicate runs (skip set).

Mirrors the patterns in lib/writers.py (line 31 dedup, line 78 dedup).
"""
from __future__ import annotations

from . import auth, sheets

COMPANIES_TAB = "Companies"
COMPANIES_HEADER = [
    "Source Company",
    "Source Company Kind",
    "Region",
    "Similar Company Name",
    "Industry",
    "Website URL",
    "Why Similar",
    "Generated At",
    "Status",
]
COMPANIES_DEDUP_COLS = ["Source Company", "Similar Company Name"]

POC_TAB = "POC"
POC_HEADER = [
    "Source Company",
    "Target Company Name",
    "Target Company Website",
    "Sought Job Titles",
    "POC Full Name",
    "Job Title",
    "Email",
    "LinkedIn URL",
    "Location",
    "Other Contact Info",
    "Status",
    "Research Sources",
    "Enrichment Source",
    "Generated At",
]
POC_DEDUP_COLS = ["Target Company Name", "POC Full Name"]


def _ensure_header(sh, tab_name: str, header: list[str]):
    """Open the tab (creating it if missing) and bootstrap the header row if blank.
    Returns the worksheet + the live header list.
    """
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=max(len(header), 26))
    live = ws.row_values(1)
    if not live:
        ws.update("A1", [header])
        live = header[:]
    return ws, live


def write_companies(rows: list[dict]) -> dict:
    """Append similar-company rows to the Companies tab. Idempotent on
    (Source Company, Similar Company Name).
    """
    secrets = auth.load_secrets()
    sh = auth.open_adhoc_sheet(secrets)
    ws, header = _ensure_header(sh, COMPANIES_TAB, COMPANIES_HEADER)
    existing = sheets.build_skip_set(
        sheets.get_records(sh, COMPANIES_TAB),
        COMPANIES_DEDUP_COLS,
    )
    new_rows = []
    skipped = 0
    for r in rows:
        key = tuple((r.get(c) or "").strip().lower() for c in COMPANIES_DEDUP_COLS)
        if not all(key) or key in existing:
            skipped += 1
            continue
        new_rows.append(r)
        existing.add(key)
    appended = sheets.append_rows_by_header(ws, header, new_rows)
    return {
        "tab": COMPANIES_TAB,
        "appended": appended,
        "skipped_existing": skipped,
    }


def write_pocs(rows: list[dict]) -> dict:
    """Append POC rows to the POC tab. Idempotent on
    (Target Company Name, POC Full Name).
    """
    secrets = auth.load_secrets()
    sh = auth.open_adhoc_sheet(secrets)
    ws, header = _ensure_header(sh, POC_TAB, POC_HEADER)
    existing = sheets.build_skip_set(
        sheets.get_records(sh, POC_TAB),
        POC_DEDUP_COLS,
    )
    new_rows = []
    skipped = 0
    for r in rows:
        key = tuple((r.get(c) or "").strip().lower() for c in POC_DEDUP_COLS)
        if not all(key) or key in existing:
            skipped += 1
            continue
        new_rows.append(r)
        existing.add(key)
    appended = sheets.append_rows_by_header(ws, header, new_rows)
    return {
        "tab": POC_TAB,
        "appended": appended,
        "skipped_existing": skipped,
    }
