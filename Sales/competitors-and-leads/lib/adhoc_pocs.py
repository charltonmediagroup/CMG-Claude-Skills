"""Ad-hoc POC collector. Powers /find-company-pocs.

Generalised version of phase2_pocs: takes a list of target companies + a list
of sought job titles + an optional region, then hits Tavily/Apify/Hunter with
those filters (instead of the hardcoded marketing/comms/APAC ones).

Claude reads the resulting JSON and applies prompts.ADHOC_POCS_EXTRACT_USER_TEMPLATE
to produce structured POC rows for the POC tab.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import auth
from .platforms import apify, hunter, tavily


def _empty_block(target_company: str, target_website: str, reason: str) -> dict:
    return {
        "target_company": target_company,
        "target_website": target_website,
        "linkedin_company_url": "",
        "apify_employees": [],
        "apify_profiles": [],
        "team_page_search": {},
        "contacts_search": {},
        "hunter_emails": [],
        "skipped_reason": reason,
    }


HUNTER_VALID_DEPARTMENTS = {
    "executive", "it", "finance", "management", "sales", "legal", "support",
    "hr", "marketing", "communication", "education", "design", "health", "operations",
}


def _collect_one(secrets: dict, *, source_company: str, target_company: str,
                 target_website: str, sought_titles: list[str],
                 region: str | None, hunter_departments: list[str] | None) -> dict:
    block = _empty_block(target_company, target_website, reason="")
    block["source_company"] = source_company

    # 1. Tavily — find LinkedIn company URL
    try:
        block["linkedin_company_url"] = tavily.find_linkedin_company_url(
            secrets["tavily"], target_company, target_website
        ) or ""
    except Exception as exc:
        block["skipped_reason"] = f"tavily linkedin lookup failed: {exc}"

    # 2 + 3. Apify — only if we found a LinkedIn URL.
    # Pass user-supplied titles + region so the LinkedIn pull is filtered to roles
    # the user actually wants. region=None => no location filter (global).
    if block["linkedin_company_url"]:
        try:
            employees = apify.get_company_employees(
                secrets["apify"], block["linkedin_company_url"],
                job_titles=sought_titles or None,
                locations=[region] if region and region.lower() != "global" else None,
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

    # 4. Tavily — team / about-us page (general — not title-specific)
    try:
        block["team_page_search"] = tavily.search(
            secrets["tavily"],
            f"{target_company} about us our team leadership management",
            search_depth="advanced", include_answer=True, max_results=3,
        )
    except Exception as exc:
        block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; tavily team page failed: {exc}"

    # 5. Tavily — contacts query, templated with the user's titles
    try:
        title_blob = " ".join((sought_titles or [])[:3])
        region_blob = "" if not region or region.lower() == "global" else f" {region}"
        contacts_query = f"{target_company} {title_blob}{region_blob}".strip()
        block["contacts_search"] = tavily.search(
            secrets["tavily"], contacts_query,
            search_depth="advanced", include_answer=True, max_results=5,
        )
    except Exception as exc:
        block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; tavily contacts failed: {exc}"

    # 6. Hunter.io — domain email search.
    # When hunter_departments is provided, filter Hunter server-side to those
    # departments so the free-tier 10-email cap is spent on the right function.
    # When None, no filter is applied and Claude post-filters from the raw 10.
    # limit=10 is the Hunter free-tier cap; the API silently clamps higher values.
    domain = hunter.domain_from_url(target_website)
    if domain:
        try:
            dept_param = ",".join(hunter_departments) if hunter_departments else None
            payload = hunter.domain_search(
                secrets["hunter"], domain, department=dept_param, limit=10,
            )
            block["hunter_emails"] = (payload.get("data") or {}).get("emails") or []
        except Exception as exc:
            block["skipped_reason"] = (block.get("skipped_reason") or "") + f"; hunter failed: {exc}"

    return block


def collect(*, companies: list[dict], sought_titles: list[str],
            region: str | None = None,
            hunter_departments: list[str] | None = None,
            dry_run: bool = False) -> dict:
    """
    companies: list of dicts with at least 'name' and 'website'. Optionally
        a 'source_company' key — used by the combined skill to tag POCs back
        to the original company they were searched against. Defaults to the
        target company name when missing.
    sought_titles: list of free-text job titles. Passed directly to Apify and
        baked into the Tavily contacts query.
    region: optional string. None or "Global" => no geographic filter.
    hunter_departments: optional list of Hunter.io department codes to filter
        the domain search by (must be from HUNTER_VALID_DEPARTMENTS). When
        omitted/None, Hunter is called unfiltered and Claude post-filters.
    """
    # Validate hunter_departments early so a bad CLI value fails fast, not after
    # the Tavily/Apify spend has burned.
    cleaned_depts: list[str] | None = None
    if hunter_departments:
        invalid = [d for d in hunter_departments if d not in HUNTER_VALID_DEPARTMENTS]
        if invalid:
            raise ValueError(
                f"Invalid Hunter departments: {invalid}. "
                f"Must be from: {sorted(HUNTER_VALID_DEPARTMENTS)}"
            )
        cleaned_depts = list(hunter_departments)

    secrets = auth.load_secrets()
    payload: dict = {
        "generated_at": date.today().isoformat(),
        "sought_titles": list(sought_titles or []),
        "region": (region or "").strip() or "Global",
        "hunter_departments": cleaned_depts or [],
        "candidates": [],
    }
    if dry_run:
        payload["candidates"] = [
            {"target_company": c.get("name", ""), "target_website": c.get("website", ""),
             "current_status": "dry-run"}
            for c in companies
        ]
        return payload
    for c in companies:
        target_company = (c.get("name") or "").strip()
        target_website = (c.get("website") or "").strip()
        source_company = (c.get("source_company") or target_company).strip()
        if not target_company:
            continue
        payload["candidates"].append(_collect_one(
            secrets,
            source_company=source_company,
            target_company=target_company,
            target_website=target_website,
            sought_titles=list(sought_titles or []),
            region=region,
            hunter_departments=cleaned_depts,
        ))
    return payload


def write_context(payload: dict, out_path: Path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
