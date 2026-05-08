---
name: sales-find-pocs
description: Find marketing/communications POCs at every Competitor row whose Status is not 'pocs_found' / 'no_pocs' / 'email_drafted'. Hits Tavily (LinkedIn URL), Apify (LinkedIn employees + profiles with email search), Tavily (team page), Tavily (contacts), Hunter.io (domain emails). Claude merges and dedupes. Appends rows to the POCs tab. Mirrors Phase 2 of the n8n 'Sales - Competitors and Leads' workflow. Use when the user asks to find POCs, find marketing contacts, /sales-find-pocs, or extend the pipeline after Phase 1.
---

# /sales-find-pocs

Phase 2 of the competitors-and-leads pipeline. For each unprocessed Competitor row, gather raw POC research from Tavily + Apify + Hunter.io, then have Claude extract a clean POC list.

## Runbook

### Step 1 — Dry-run candidate count

```
python ~/.claude/competitors-and-leads/run.py phase2-collect --dry-run
```

This is the highest-cost phase: each candidate fires ~6 API calls (Tavily ×3, Apify ×2, Hunter ×1). Apify is the slowest (up to 2 minutes per competitor). **Always confirm with the user before doing >10 candidates.**

### Step 2 — Collect raw research

```
python ~/.claude/competitors-and-leads/run.py phase2-collect
```

Writes `~/.claude/competitors-and-leads/output/phase2_pocs_context.json`. Each candidate block contains: `linkedin_company_url`, `apify_employees`, `apify_profiles`, `team_page_search`, `contacts_search`, `hunter_emails`, `skipped_reason`.

### Step 3 — Reasoning (you, Claude)

For each candidate block, apply the prompt in `~/.claude/competitors-and-leads/lib/prompts.py` (`PHASE2_EXTRACT_USER_TEMPLATE`) — copied verbatim from n8n node `p2-extract-pocs-ai`.

Build the `all_content` field by concatenating: Tavily team-page summaries, Tavily contacts summaries, Apify employee headlines, and any Hunter.io emails the dedup didn't already cover.

The Apify path already returns structured POC data (`firstName`, `lastName`, `headline`, `experience`, `linkedinUrl`). The AI extraction is the catch-all for cases where Tavily found people the Apify scrape missed (e.g. listed on team pages but not surfaced in LinkedIn searches).

Merge the two sources, dedupe by full name (lowercased), and prefer the row with a real email over one with `email not found`. Final POC schema (matches the live POCs tab):

```json
{
  "Client Company": "<from competitor row>",
  "Competitor Name": "...",
  "Competitor Website": "...",
  "POC Full Name": "...",
  "Job Title": "...",
  "Email": "<email or 'email not found'>",
  "LinkedIn URL": "...",
  "Location (APAC)": "...",
  "Other Contact Info": "<e.g. phone>",
  "Status": "new",
  "Research Sources": "<\\n-separated list of source URLs>",
  "Enrichment Source": "Apify/LinkedIn, Tavily/AI, Hunter.io"
}
```

If a candidate produced ZERO POCs after extraction, add its `Competitor Name` to a `competitors_with_no_pocs` array so the writer flips its Status to `no_pocs`.

Save merged output to `~/.claude/competitors-and-leads/output/phase2_drafts.json`:

```json
{
  "pocs": [{...}],
  "competitors_with_no_pocs": ["Competitor X", "Competitor Y"]
}
```

For batches over 5 candidates, delegate the per-competitor extraction to Explore subagents in parallel.

### Step 4 — Show your work + write

Print per-competitor POC counts. Ask the user to confirm. Then:

```
python ~/.claude/competitors-and-leads/run.py phase2-write --input ~/.claude/competitors-and-leads/output/phase2_drafts.json
```

This appends new POC rows (idempotent), flips `Competitor.Status='pocs_found'` for competitors that got POCs, and `'no_pocs'` for those that didn't.

## Verification

`phase2-collect --dry-run` should now exclude the competitors you just processed.

## Notes

- The Apify employee scrape is filtered by `MARKETING_TITLES` and `APAC_LOCATIONS` (defined in `lib/platforms/apify.py`) — same lists as the n8n workflow.
- If a competitor has no findable LinkedIn company URL, the Apify steps are skipped and the AI extraction works only off Tavily team-page + contacts results.
- Hunter.io results are pre-filtered server-side to `marketing,communication` departments.
