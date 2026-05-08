"""Phase 2 collector: for each Competitor row not yet processed,
hit Tavily + Apify + Hunter to assemble raw POC research context.

Claude reads the resulting JSON and applies the n8n
p2-extract-pocs-ai prompt to produce structured POC rows.
"""
from __future__ import annotations

import json
from datetime import date

from . import auth
from .platforms import apify, hunter, tavily

SKIP_STATUSES = {"pocs_found", "no_pocs", "email_drafted"}


def list_candidates(sh) -> list[dict]:
    rows = sh.worksheet("Competitors").get_all_records()
    return [r for r in rows if (r.get("Status") or "").strip().lower() not in SKIP_STATUSES]


def _empty_block(competitor: dict, reason: str) -> dict:
    return {
        "client_company": competitor.get("Client Company", ""),
        "competitor_name": competitor.get("Competitor Name", ""),
        "competitor_website": competitor.get("Website URL", ""),
        "linkedin_company_url": "",
        "apify_employees": [],
        "apify_profiles": [],
        "team_page_search": {},
        "contacts_search": {},
        "hunter_emails": [],
        "skipped_reason": reason,
    }


def _collect_one(secrets: dict, competitor: dict) -> dict:
    name = competitor.get("Competitor Name", "")
    website = competitor.get("Website URL", "")

    block = _empty_block(competitor, reason="")

    # 1. Tavily — find LinkedIn company URL
    try:
        block["linkedin_company_url"] = tavily.find_linkedin_company_url(
            secrets["tavily"], name, website
        ) or ""
    except Exception as exc:
        block["skipped_reason"] = f"tavily linkedin lookup failed: {exc}"

    # 2 + 3. Apify — only if we found a LinkedIn URL
    if block["linkedin_company_url"]:
        try:
            employees = apify.get_company_employees(
                secrets["apify"], block["linkedin_company_url"]
            )
            block["apify_employees"] = employees
            profile_urls = []
            for e in employees:
                u = (e.get("linkedinUrl") or "").strip()
                if u:
                    profile_urls.append(u)
            if profile_urls:
                block["apify_profiles"] = apify.enrich_profiles(secrets["apify"], profile_urls)
        except Exception as exc:
            block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; apify failed: {exc}"

    # 4. Tavily — team / about-us page
    try:
        block["team_page_search"] = tavily.search(
            secrets["tavily"],
            f"{name} about us our team leadership management",
            search_depth="advanced", include_answer=True, max_results=3,
        )
    except Exception as exc:
        block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; tavily team page failed: {exc}"

    # 5. Tavily — contacts
    try:
        block["contacts_search"] = tavily.search(
            secrets["tavily"],
            f"{name} marketing director digital marketing manager APAC Asia",
            search_depth="advanced", include_answer=True, max_results=5,
        )
    except Exception as exc:
        block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; tavily contacts failed: {exc}"

    # 6. Hunter.io — domain email search
    domain = hunter.domain_from_url(website)
    if domain:
        try:
            payload = hunter.domain_search(secrets["hunter"], domain)
            block["hunter_emails"] = (payload.get("data") or {}).get("emails") or []
        except Exception as exc:
            block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; hunter failed: {exc}"

    return block


def collect(dry_run: bool = False) -> dict:
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    candidates = list_candidates(sh)
    payload = {"generated_at": date.today().isoformat(), "candidates": []}
    if dry_run:
        payload["candidates"] = [
            {"client_company": c.get("Client Company", ""),
             "competitor_name": c.get("Competitor Name", ""),
             "current_status": c.get("Status", "")}
            for c in candidates
        ]
        return payload
    for c in candidates:
        payload["candidates"].append(_collect_one(secrets, c))
    return payload


def write_context(payload: dict, out_path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
