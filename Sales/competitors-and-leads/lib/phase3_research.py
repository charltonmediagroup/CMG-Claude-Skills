"""Phase 3 collector: for each Competitor row whose POCs lack research,
run two SerpAPI searches and emit context.

Claude reads the JSON and applies the n8n p2-research-agent prompt to
produce recent_activity + collaboration_opportunities + summary + sources.
"""
from __future__ import annotations

import json
from datetime import date

from . import auth
from .platforms import serpapi


def list_candidates(sh) -> list[dict]:
    """Competitors with Status='pocs_found' whose POC rows have empty
    Website Research Summary."""
    competitors = sh.worksheet("Competitors").get_all_records()
    pocs = sh.worksheet("POCs").get_all_records()
    research_filled = set()
    for p in pocs:
        if (p.get("Website Research Summary") or "").strip():
            research_filled.add((p.get("Competitor Name") or "").strip().lower())
    out = []
    for c in competitors:
        status = (c.get("Status") or "").strip().lower()
        name = (c.get("Competitor Name") or "").strip()
        if status == "pocs_found" and name.lower() not in research_filled:
            out.append(c)
    return out


def _collect_one(secrets: dict, competitor: dict) -> dict:
    name = competitor.get("Competitor Name", "")
    website = competitor.get("Website URL", "")
    today = date.today().isoformat()

    queries = [
        f'"{name}" product launch OR announcement OR expansion OR funding 2025 2026',
        f'"{name}" executive OR leadership OR partnership OR event APAC Asia 2025 2026',
    ]
    searches = []
    for q in queries:
        try:
            payload = serpapi.search(secrets["serpapi"], q, num=8)
            searches.append({"query": q, "results": serpapi.organic_summaries(payload)})
        except Exception as exc:
            searches.append({"query": q, "error": str(exc), "results": []})

    return {
        "client_company": competitor.get("Client Company", ""),
        "competitor_name": name,
        "competitor_website": website,
        "today": today,
        "searches": searches,
    }


def collect(dry_run: bool = False) -> dict:
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    candidates = list_candidates(sh)
    payload = {"generated_at": date.today().isoformat(), "candidates": []}
    if dry_run:
        payload["candidates"] = [
            {"competitor_name": c.get("Competitor Name", "")} for c in candidates
        ]
        return payload
    for c in candidates:
        payload["candidates"].append(_collect_one(secrets, c))
    return payload


def write_context(payload: dict, out_path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
