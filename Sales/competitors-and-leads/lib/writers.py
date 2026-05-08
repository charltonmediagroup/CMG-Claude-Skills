"""Sheet writers for each phase. Each writer:
- Re-reads the destination tab to build a skip-set
- Appends only new rows
- Updates Status fields where applicable

Migrated from scripts/draft_emails_phase_c_write.py and generalised to
all four phases.
"""
from __future__ import annotations

from datetime import date

from . import auth, sheets


# ---------------------------------------------------------------------------
# Phase 1 — write competitors + flip SBR Checked
# ---------------------------------------------------------------------------

def write_competitors(competitors: list[dict]) -> dict:
    """Append rows to Competitors tab and mark SBR.Checked='Yes' for clients
    that got at least one new competitor row.

    Each input dict must include: Client Company, Competitor Name, Industry,
    Website URL, Why Competitor, Status (will default to 'new').
    """
    sh = auth.open_sheet()
    comp_ws = sh.worksheet("Competitors")
    header = sheets.get_header(sh, "Competitors")
    existing = sheets.get_records(sh, "Competitors")
    skip = sheets.build_skip_set(existing, ["Client Company", "Competitor Name"])

    new_rows = []
    for r in competitors:
        key = ((r.get("Client Company") or "").strip().lower(),
               (r.get("Competitor Name") or "").strip().lower())
        if not all(key) or key in skip:
            continue
        r.setdefault("Status", "new")
        new_rows.append(r)

    appended = sheets.append_rows_by_header(comp_ws, header, new_rows)

    # Flip SBR.Checked to 'Yes' for any client that just got new rows
    sbr_ws = sh.worksheet("SBR")
    sbr_rows = sbr_ws.get_all_values()
    sbr_header = sbr_rows[0] if sbr_rows else []
    try:
        client_idx = sbr_header.index("Company Name")
        checked_idx = sbr_header.index("Checked")
    except ValueError:
        return {"appended": appended, "sbr_marked": 0}
    clients_with_new = {(r.get("Client Company") or "").strip().lower() for r in new_rows}
    cells = []
    import gspread
    for r_i, row in enumerate(sbr_rows[1:], start=2):
        if max(client_idx, checked_idx) >= len(row):
            continue
        if (row[client_idx] or "").strip().lower() in clients_with_new:
            if (row[checked_idx] or "").strip().lower() != "yes":
                cells.append(gspread.Cell(row=r_i, col=checked_idx + 1, value="Yes"))
    if cells:
        sbr_ws.update_cells(cells, value_input_option="RAW")
    return {"appended": appended, "sbr_marked": len(cells)}


# ---------------------------------------------------------------------------
# Phase 2 — write POCs + flip Competitor.Status
# ---------------------------------------------------------------------------

def write_pocs(pocs: list[dict], competitors_with_no_pocs: list[str] | None = None) -> dict:
    """Append rows to POCs tab. Flip Competitor.Status='pocs_found' (or
    'no_pocs' for the names in competitors_with_no_pocs)."""
    sh = auth.open_sheet()
    ws = sh.worksheet("POCs")
    header = sheets.get_header(sh, "POCs")
    existing = sheets.get_records(sh, "POCs")
    skip = sheets.build_skip_set(existing, ["Competitor Name", "POC Full Name"])

    new_rows = []
    for r in pocs:
        key = ((r.get("Competitor Name") or "").strip().lower(),
               (r.get("POC Full Name") or "").strip().lower())
        if not all(key) or key in skip:
            continue
        r.setdefault("Status", "new")
        new_rows.append(r)

    appended = sheets.append_rows_by_header(ws, header, new_rows)

    # Flip Competitor.Status
    comp_ws = sh.worksheet("Competitors")
    comp_header = sheets.get_header(sh, "Competitors")

    found_names = {(r.get("Competitor Name") or "").strip().lower() for r in new_rows}
    no_pocs_names = {(n or "").strip().lower() for n in (competitors_with_no_pocs or [])}

    pocs_found_updated = sheets.update_status(
        comp_ws, comp_header, ["Competitor Name"], [(n,) for n in found_names], "pocs_found"
    ) if found_names else 0

    no_pocs_updated = sheets.update_status(
        comp_ws, comp_header, ["Competitor Name"], [(n,) for n in no_pocs_names], "no_pocs"
    ) if no_pocs_names else 0

    return {
        "appended": appended,
        "competitors_marked_pocs_found": pocs_found_updated,
        "competitors_marked_no_pocs": no_pocs_updated,
    }


# ---------------------------------------------------------------------------
# Phase 3 — update POCs with research results
# ---------------------------------------------------------------------------

def write_research(research_by_competitor: dict) -> dict:
    """Update POCs tab rows with research fields.

    research_by_competitor is a dict keyed by competitor_name (lowercase) ->
    {website_research_summary, recent_activity, suggested_collaborations,
     research_sources}. All POCs of that competitor get the same values.
    """
    sh = auth.open_sheet()
    ws = sh.worksheet("POCs")
    rows = ws.get_all_values()
    if not rows:
        return {"updated": 0}
    header = rows[0]
    try:
        comp_idx = header.index("Competitor Name")
        summary_idx = header.index("Website Research Summary")
        activity_idx = header.index("Recent Activity")
        collab_idx = header.index("Suggested Collaborations")
    except ValueError as exc:
        raise RuntimeError(f"POCs header missing column: {exc}") from exc
    sources_idx = header.index("Research Sources") if "Research Sources" in header else None

    import gspread
    cells = []
    updated = 0
    for r_i, row in enumerate(rows[1:], start=2):
        if comp_idx >= len(row):
            continue
        comp = (row[comp_idx] or "").strip().lower()
        data = research_by_competitor.get(comp)
        if not data:
            continue
        cells.append(gspread.Cell(row=r_i, col=summary_idx + 1, value=data.get("website_research_summary", "")))
        cells.append(gspread.Cell(row=r_i, col=activity_idx + 1, value=data.get("recent_activity", "")))
        cells.append(gspread.Cell(row=r_i, col=collab_idx + 1, value=data.get("suggested_collaborations", "")))
        if sources_idx is not None:
            cells.append(gspread.Cell(row=r_i, col=sources_idx + 1, value=data.get("research_sources", "")))
        updated += 1
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Phase 4 — write Email Drafts + flip POCs/Competitor statuses
# (Migrated from scripts/draft_emails_phase_c_write.py)
# ---------------------------------------------------------------------------

def write_drafts(drafts: list[dict]) -> dict:
    sh = auth.open_sheet()
    today = date.today().isoformat()
    for d in drafts:
        d.setdefault("Created Date", today)
        d.setdefault("Status", "draft")

    drafts_ws = sh.worksheet("Email Drafts")
    header = sheets.get_header(sh, "Email Drafts")
    existing = sheets.get_records(sh, "Email Drafts")
    skip = sheets.build_skip_set(existing, ["Competitor Name", "POC Name"], require_col="Email Body")

    new_rows = []
    for d in drafts:
        key = ((d.get("Competitor Name") or "").strip().lower(),
               (d.get("POC Name") or "").strip().lower())
        if not all(key) or key in skip:
            continue
        new_rows.append(d)

    appended = sheets.append_rows_by_header(drafts_ws, header, new_rows)

    if not new_rows:
        return {"appended": 0, "pocs_updated": 0, "competitors_updated": 0}

    poc_ws = sh.worksheet("POCs")
    poc_header = sheets.get_header(sh, "POCs")
    poc_keys = [((d.get("Competitor Name") or "").strip().lower(),
                 (d.get("POC Name") or "").strip().lower()) for d in new_rows]
    pocs_updated = sheets.update_status(
        poc_ws, poc_header, ["Competitor Name", "POC Full Name"], poc_keys, "email_drafted"
    )

    comp_ws = sh.worksheet("Competitors")
    comp_header = sheets.get_header(sh, "Competitors")
    comp_keys = [(c,) for c in {(d.get("Competitor Name") or "").strip().lower() for d in new_rows}]
    competitors_updated = sheets.update_status(
        comp_ws, comp_header, ["Competitor Name"], comp_keys, "pocs_found"
    )

    return {
        "appended": appended,
        "pocs_updated": pocs_updated,
        "competitors_updated": competitors_updated,
    }
