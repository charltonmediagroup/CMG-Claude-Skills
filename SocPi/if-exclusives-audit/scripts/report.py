"""Render the audit report from matches.json.

Status hierarchy (per row):
  DUPLICATE ISSUE — any platform has >1 actual posted match (overrides all)
  COMPLETE        — all 4 platforms have an actual posted match
  PARTIAL         — 1-3 platforms have actual posted matches
  SCHEDULED       — no posted matches but at least one platform has a
                    scheduled match
  MISSING         — nothing posted, nothing scheduled

Per-platform cell logic for the markdown:
  posted match exists           → "[OK]"
  scheduled match exists (only) → "[SCH]"
  neither                        → "[X]"
"""

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from rapidfuzz import fuzz


PLATFORMS = [("facebook", "Facebook"), ("instagram", "Instagram"),
             ("linkedin", "LinkedIn"), ("twitter", "X")]


def parse_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def derive_status(article):
    posted = article.get("posted_matches") or {}
    scheduled = article.get("scheduled_matches") or {}
    fuzzy = article.get("fuzzy_matches") or {}

    posted_platforms: list[str] = []
    scheduled_platforms: list[str] = []
    duplicate = False

    for key, _ in PLATFORMS:
        # Fuzzy results are split by their original kind.
        fuzzy_posted = [m for m in (fuzzy.get(key) or []) if m.get("kind") != "scheduled"]
        fuzzy_scheduled = [m for m in (fuzzy.get(key) or []) if m.get("kind") == "scheduled"]
        all_posted = list(posted.get(key) or []) + fuzzy_posted
        all_scheduled = list(scheduled.get(key) or []) + fuzzy_scheduled
        if all_posted:
            posted_platforms.append(key)
            if len(all_posted) > 1:
                duplicate = True
        elif all_scheduled:
            scheduled_platforms.append(key)

    if duplicate:
        status = "DUPLICATE ISSUE"
    elif len(posted_platforms) == 4:
        status = "COMPLETE"
    elif posted_platforms:
        status = "PARTIAL"
    elif scheduled_platforms:
        status = "SCHEDULED"
    else:
        status = "MISSING"
    return status, posted_platforms, scheduled_platforms, duplicate


def derive_notes(article):
    notes = []
    pub_dt = parse_iso(article.get("publishDate"))
    title = article.get("title") or ""

    for key, _ in PLATFORMS:
        if article.get("fuzzy_matches", {}).get(key):
            notes.append(f"{key}:via:fuzzy")
        for post in article.get("posted_matches", {}).get(key) or []:
            desc = post.get("description") or ""
            if not desc.strip():
                notes.append(f"{key}:caption-empty")
            if pub_dt:
                post_dt = parse_iso(post.get("publishedAt"))
                if post_dt and (post_dt - pub_dt).total_seconds() > 48 * 3600:
                    notes.append(f"{key}:delay>48h")
            if title and desc and fuzz.token_set_ratio(title, desc) < 50:
                notes.append(f"{key}:caption-mismatch")
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matches")
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-csv", required=True)
    args = ap.parse_args()

    articles = json.loads(Path(args.matches).read_text(encoding="utf-8"))
    today = dt.date.today()

    rows = []
    counts = {"COMPLETE": 0, "PARTIAL": 0, "SCHEDULED": 0,
              "MISSING": 0, "DUPLICATE ISSUE": 0}
    p1 = p2 = p3 = 0
    has_any_posted = 0
    has_all_posted = 0

    for a in articles:
        status, posted_set, sched_set, duplicate = derive_status(a)
        counts[status] = counts.get(status, 0) + 1

        if posted_set:
            has_any_posted += 1
        if len(posted_set) == 4 and not duplicate:
            has_all_posted += 1

        notes = derive_notes(a)
        if status == "MISSING":
            p1 += 1
        elif status in ("PARTIAL", "DUPLICATE ISSUE"):
            p2 += 1
        if notes:
            p3 += 1

        cells = {}
        for key, _ in PLATFORMS:
            if key in posted_set:
                cells[key] = "[OK]"
            elif key in sched_set:
                cells[key] = "[SCH]"
            else:
                cells[key] = "[X]"

        missing = [name for key, name in PLATFORMS
                   if key not in posted_set and key not in sched_set]
        rows.append({
            "title": a.get("title") or a.get("title_guess") or a["url"],
            "url": a["url"],
            "tag": a.get("tag") or "IF/EXCLUSIVE",
            "facebook": cells["facebook"],
            "instagram": cells["instagram"],
            "linkedin": cells["linkedin"],
            "twitter": cells["twitter"],
            "covered": len(posted_set) + len(sched_set),
            "missing": ", ".join(missing) if missing else "None",
            "duplicate": "Yes" if duplicate else "No",
            "status": status,
            "notes": "; ".join(notes) if notes else "",
        })

    total = len(articles)
    match_rate = (has_any_posted / total * 100) if total else 0.0
    full_rate = (has_all_posted / total * 100) if total else 0.0

    md = []
    md.append(f"# IF & EXCLUSIVE Distribution Audit — {today.isoformat()}")
    md.append("")
    md.append("## System Design")
    md.append("")
    md.append(
        "Source: `Commercial SocPi - Links` Google Sheet, tab `IF & Exclusives`. "
        "SocialPilot `DeliveredPosts` AND `QueuedPosts` are queried per "
        "publication × platform (FB/IG/LI/X). URL-first matching with "
        "short-link resolution; fuzzy slug↔caption fallback flagged in Notes. "
        "Per-platform cell: `[OK]` posted, `[SCH]` scheduled-only, `[X]` neither."
    )
    md.append("")
    md.append("## Audit Table")
    md.append("")
    md.append("| Article Title | Article URL | Tag | Facebook | Instagram | LinkedIn | X | Platforms Covered | Missing Platforms | Duplicate Posts | Status |")
    md.append("|---|---|---|:---:|:---:|:---:|:---:|:---:|---|:---:|---|")
    for r in rows:
        title = (r["title"] or "").replace("|", "\\|")
        url = r["url"].replace("|", "\\|")
        md.append(
            f"| {title} | <{url}> | {r['tag']} | {r['facebook']} | "
            f"{r['instagram']} | {r['linkedin']} | {r['twitter']} | "
            f"{r['covered']} | {r['missing']} | {r['duplicate']} | {r['status']} |"
        )
    md.append("")
    md.append("## Summary Metrics")
    md.append("")
    md.append(f"- **Total articles**: {total}")
    md.append(f"- **COMPLETE**: {counts.get('COMPLETE', 0)}")
    md.append(f"- **PARTIAL**: {counts.get('PARTIAL', 0)}")
    md.append(f"- **SCHEDULED**: {counts.get('SCHEDULED', 0)}")
    md.append(f"- **MISSING**: {counts.get('MISSING', 0)}")
    md.append(f"- **DUPLICATE ISSUE**: {counts.get('DUPLICATE ISSUE', 0)}")
    md.append(f"- **Posted Match Rate** (>=1 platform actually posted): {match_rate:.1f}%")
    md.append(f"- **Full Distribution Rate** (all 4 platforms posted): {full_rate:.1f}%")
    md.append("")
    md.append("### Alert tiers")
    md.append(f"- **P1** (MISSING): {p1}")
    md.append(f"- **P2** (PARTIAL or DUPLICATE ISSUE): {p2}")
    md.append(f"- **P3** (any caption / delay / fuzzy flag): {p3}")
    md.append("")

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(md), encoding="utf-8")

    with Path(args.out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Article Title", "Article URL", "Tag",
                    "Facebook", "Instagram", "LinkedIn", "X",
                    "Platforms Covered", "Missing Platforms", "Duplicate Posts",
                    "Status", "Notes"])
        for r in rows:
            w.writerow([r["title"], r["url"], r["tag"],
                        r["facebook"], r["instagram"], r["linkedin"], r["twitter"],
                        r["covered"], r["missing"], r["duplicate"],
                        r["status"], r["notes"]])

    print(f"Wrote {args.out_md} and {args.out_csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
