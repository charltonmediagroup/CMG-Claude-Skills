"""Phase 1 collector: for each unprocessed SBR client, run a SerpAPI search
and emit a JSON context file Claude reads to extract competitors.

Mirrors the data n8n's p1-agent (Find Competitors Agent) gets from the
attached SerpAPI tool.
"""
from __future__ import annotations

import json
from datetime import date

from . import auth
from .platforms import serpapi


def list_candidates(sh) -> list[dict]:
    """Return SBR rows where Checked != 'Yes' (case-insensitive)."""
    rows = sh.worksheet("SBR").get_all_records()
    return [r for r in rows if (r.get("Checked") or "").strip().lower() != "yes"]


def collect(dry_run: bool = False) -> dict:
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    candidates = list_candidates(sh)
    payload = {"generated_at": date.today().isoformat(), "candidates": []}
    if dry_run:
        payload["candidates"] = [{"company_name": c.get("Company Name", "")} for c in candidates]
        return payload

    for c in candidates:
        company = (c.get("Company Name") or "").strip()
        if not company:
            continue
        query = f"{company} APAC competitors direct"
        results = serpapi.search(secrets["serpapi"], query, num=8)
        payload["candidates"].append({
            "company_name": company,
            "year": c.get("Year"),
            "search_query": query,
            "search_results": serpapi.organic_summaries(results),
        })

    return payload


def write_context(payload: dict, out_path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
