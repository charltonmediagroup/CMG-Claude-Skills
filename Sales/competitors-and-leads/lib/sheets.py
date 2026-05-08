"""Read/write helpers for the 'Existing Clients (2021 to 2025)' sheet tabs.

Tabs:
  - SBR             (clients: Year, Company Name, Checked)
  - Competitors     (Client Company, Competitor Name, Industry, Website URL, Why Competitor, Status)
  - POCs            (Competitor Name, Competitor Website, POC Full Name, ..., Client Company, ..., Status)
  - Email Drafts    (Client Company, Competitor Name, POC Name, ..., Status, Created Date, Revised Version, Approved)
  - Media Kits      (Publication, Type, Industries, Markets, Summary)

All write helpers re-read the destination tab right before writing so they
are idempotent against concurrent edits.
"""
from __future__ import annotations

from typing import Iterable

import gspread


def get_records(sh, tab_name: str) -> list[dict]:
    return sh.worksheet(tab_name).get_all_records()


def get_header(sh, tab_name: str) -> list[str]:
    return sh.worksheet(tab_name).row_values(1)


def append_rows_by_header(ws, header: list[str], rows: list[dict]) -> int:
    """Append rows mapped to the live header; returns count appended."""
    if not rows:
        return 0
    payload = []
    for r in rows:
        payload.append([r.get(col, "") for col in header])
    ws.append_rows(payload, value_input_option="RAW")
    return len(payload)


def update_status(ws, header: list[str], match_cols: list[str],
                  matches: Iterable[tuple], new_status: str) -> int:
    """Set Status to new_status for rows whose tuple of (match_cols values) is in `matches`.
    Returns number of rows updated. Skips rows already at new_status.
    """
    rows = ws.get_all_values()
    if not rows:
        return 0
    try:
        idxs = [header.index(c) for c in match_cols]
        status_idx = header.index("Status")
    except ValueError as exc:
        raise RuntimeError(f"Tab missing expected column: {exc}") from exc
    target_set = {tuple(s.strip().lower() for s in m) for m in matches}
    cells = []
    matched = 0
    for r_i, row in enumerate(rows[1:], start=2):
        if max(*idxs, status_idx) >= len(row):
            continue
        key = tuple(row[i].strip().lower() for i in idxs)
        if key in target_set:
            matched += 1
            if row[status_idx].strip().lower() != new_status.lower():
                cells.append(gspread.Cell(row=r_i, col=status_idx + 1, value=new_status))
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
    return matched


def build_skip_set(records: list[dict], cols: list[str], require_col: str | None = None) -> set[tuple]:
    """Build a set of lowercased tuples from `cols` for rows where `require_col` (if given) is non-empty."""
    s = set()
    for r in records:
        if require_col and not (r.get(require_col) or "").strip():
            continue
        key = tuple((r.get(c) or "").strip().lower() for c in cols)
        if all(key):
            s.add(key)
    return s
