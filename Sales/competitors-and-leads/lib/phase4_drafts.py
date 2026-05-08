"""Phase 4 collector: filter POCs that need an email draft + score
matching media kits.

Migrated from scripts/draft_emails_phase_a_read.py with the per-client
filter dropped (batch mode now per user decision).
"""
from __future__ import annotations

import json
from datetime import date

from . import auth


def is_valid_email(value: str) -> bool:
    v = (value or "").strip().lower()
    return bool(v) and v != "email not found" and "@" in v


def score_media_kit(kit: dict, competitor_name: str, suggested_collabs: str,
                    recent_activity: str, location: str) -> int:
    """Mirror p2-select-kits scoring from the n8n workflow."""
    score = 0
    industries = [s.strip() for s in (kit.get("Industries") or kit.get("industries") or "").lower().split(",")]
    markets = [s.strip() for s in (kit.get("Markets") or kit.get("markets") or "").lower().split(",")]
    cn = (competitor_name or "").lower()
    sc = (suggested_collabs or "").lower()
    ra = (recent_activity or "").lower()
    loc = (location or "").lower()
    for ind in industries:
        if ind and (ind in cn or ind in sc or ind in ra):
            score += 3
    for mkt in markets:
        if mkt and mkt in loc:
            score += 1
    if "general business" in (kit.get("Industries") or kit.get("industries") or "").lower():
        score += 1
    return score


def select_media_kits(all_kits: list[dict], poc: dict) -> tuple[list[dict], str]:
    competitor_name = poc.get("Competitor Name", "")
    suggested_collabs = poc.get("Suggested Collaborations", "")
    recent_activity = poc.get("Recent Activity", "")
    location = poc.get("Location (APAC)", "")
    scored = []
    for k in all_kits:
        s = score_media_kit(k, competitor_name, suggested_collabs, recent_activity, location)
        scored.append({**k, "score": s})
    scored.sort(key=lambda r: r["score"], reverse=True)
    top = [r for r in scored if r["score"] > 0][:4]
    if not top:
        top = scored[:2]
    matched_text_parts = []
    matched_names = []
    for k in top:
        pub = k.get("Publication") or k.get("publication") or ""
        summary = k.get("Summary") or k.get("summary") or ""
        if pub:
            matched_names.append(pub)
        matched_text_parts.append({
            "publication": pub,
            "type": k.get("Type") or k.get("type") or "",
            "summary": summary,
            "score": k["score"],
        })
    return matched_text_parts, ", ".join(matched_names)


def list_candidates(sh) -> list[dict]:
    pocs = sh.worksheet("POCs").get_all_records()
    drafts = sh.worksheet("Email Drafts").get_all_records()
    skip = set()
    for d in drafts:
        comp = (d.get("Competitor Name") or "").strip().lower()
        name = (d.get("POC Name") or "").strip().lower()
        body = (d.get("Email Body") or "").strip()
        if comp and name and body:
            skip.add((comp, name))
    out = []
    for r in pocs:
        status = (r.get("Status") or "").strip().lower()
        comp = (r.get("Competitor Name") or "").strip().lower()
        name = (r.get("POC Full Name") or "").strip().lower()
        email = (r.get("Email") or "").strip()
        if status == "email_drafted":
            continue
        if (comp, name) in skip:
            continue
        if not is_valid_email(email):
            continue
        out.append(r)
    return out


def collect(dry_run: bool = False) -> dict:
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    candidates = list_candidates(sh)
    media_kits = sh.worksheet("Media Kits").get_all_records()
    payload = {"generated_at": date.today().isoformat(), "pocs": []}
    if dry_run:
        payload["pocs"] = [
            {"client_company": r.get("Client Company", ""),
             "competitor_name": r.get("Competitor Name", ""),
             "poc_full_name": r.get("POC Full Name", "")}
            for r in candidates
        ]
        return payload
    for r in candidates:
        kits_matched, kits_str = select_media_kits(media_kits, r)
        payload["pocs"].append({
            "client_company": r.get("Client Company", ""),
            "competitor_name": r.get("Competitor Name", ""),
            "competitor_website": r.get("Competitor Website", ""),
            "poc_full_name": r.get("POC Full Name", ""),
            "job_title": r.get("Job Title", ""),
            "email": r.get("Email", ""),
            "linkedin_url": r.get("LinkedIn URL", ""),
            "location": r.get("Location (APAC)", ""),
            "website_research_summary": r.get("Website Research Summary", ""),
            "recent_activity": r.get("Recent Activity", ""),
            "suggested_collaborations": r.get("Suggested Collaborations", ""),
            "matched_media_kits": kits_matched,
            "matched_publications_string": kits_str,
        })
    return payload


def write_context(payload: dict, out_path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
