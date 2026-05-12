---
name: find-similar-companies-and-pocs
description: Run /find-similar-companies and /find-company-pocs back-to-back in one go. Takes a single company + what kind it is + casual job-title phrasing (e.g. "sales leaders", "engineering managers") + optional region. First expands the casual title input into a moderate list of LinkedIn-style variants and confirms with the user, then finds 5–10 similar/competitor companies (Companies tab), then finds POCs at each of those companies filtered by the expanded title list (POC tab). Confirmation gate between the two phases so the user can scope down before paying for the high-cost POC API calls. Use when the user wants the full ad-hoc lookup end-to-end, /find-similar-companies-and-pocs, or "find me companies like X with their VP Sales / CTO / etc. contacts".
---

# /find-similar-companies-and-pocs

Thin orchestrator that runs `/find-similar-companies` and `/find-company-pocs` back-to-back. Same ad-hoc Google Sheet (`1NpFZ2JdtZQqgWHyp5tL2uAsQJWdEWE9uvLr1OyuNiqg`) — fills both `Companies` and `POC` tabs.

## Inputs you need from the user

1. **Source company name**.
2. **What kind of company is it?** (free-text — see `/find-similar-companies` for guidance).
3. **Sought job titles** at the similar companies — casual input is fine (e.g. `"sales leaders"`, `"engineering managers and above"`). You'll expand it in Phase 0 below.
4. *(Optional)* **Region** — default `Global`.
5. *(Optional)* **Max similar companies** — default 10. (Each one fires ~6 API calls in Phase 2, so dial this down if you want to be conservative on cost.)

## Runbook

### Phase 0 — Expand the sought job titles + pick Hunter departments (REQUIRED, do this first)

Before any API calls, do two things in one confirmation step:
1. Expand the user's casual title input into a comma-separated list of literal LinkedIn-style title variants. **Use moderate expansion**: synonyms + adjacent seniority levels in the same function, NOT lateral/unrelated roles.
2. Pick 1–4 Hunter.io departments from the fixed 14 (`executive, it, finance, management, sales, legal, support, hr, marketing, communication, education, design, health, operations`) that match the user's intent. If nothing fits, omit and Hunter goes unfiltered.

Follow the tables and rules in `/find-company-pocs` SKILL.md **Step 1, 1b, 1c** (`~/.claude/skills/find-company-pocs/SKILL.md`). Show both the expanded titles and the proposed Hunter departments to the user in a single confirmation prompt, then carry the confirmed values forward as `<EXPANDED_TITLES>` and `<HUNTER_DEPTS>` for Phase C below.

Doing this up front (before Phase A) means you have one confirmation point instead of two and the user knows the full search criteria before any company list is built.

### Phase A — Find similar companies

Follow `/find-similar-companies` (`~/.claude/skills/find-similar-companies/SKILL.md`) Steps 1–4. Results land in the `Companies` tab.

After the write completes, you have `~/.claude/competitors-and-leads/output/adhoc_similar_drafts.json` with the new companies.

### Phase B — Confirmation gate

**Stop here.** Show the user the list of N similar companies and the cost projection: roughly `N × 6` API calls in the POC phase, with Apify taking up to ~2 minutes per company. Ask:

- *"Proceed with all N? Drop some? Cancel?"*

If the user wants to drop some, edit the input list down before continuing. If they cancel, stop — they still have the `Companies` tab populated.

### Phase C — Find POCs at the confirmed companies

Build the POC input file from Phase A's drafts:

```
~/.claude/competitors-and-leads/output/adhoc_pocs_input.json
```

Shape:
```json
[
  {"name": "<Similar Company Name>",
   "website": "<Website URL>",
   "source_company": "<the user's original source company>"},
  ...
]
```

Then follow `/find-company-pocs` (`~/.claude/skills/find-company-pocs/SKILL.md`) from Step 2 onward (skip its Step 1 — you already did the title expansion + Hunter dept pick in Phase 0). The `--titles` flag is the `<EXPANDED_TITLES>` list from Phase 0; the `--hunter-depts` flag is the `<HUNTER_DEPTS>` list (omit if Phase 0 omitted Hunter dept selection).

POC rows land in the `POC` tab with `Source Company` traceable back to the original company the user asked about (not the per-target company). Future audits can group "all POCs we ever found via the original Notion lookup" by filtering `Source Company = "Notion"`.

## Composability

This is just a wrapper. Power users can run the two skills directly when they want fine-grained control between the phases.

## Verification

After both phases:
1. Open the `Companies` tab — N rows for this `Source Company`.
2. Open the `POC` tab — POCs scattered across the N target companies, each row's `Source Company` field equal to the original company name, `Sought Job Titles` matching what the user asked for.

## Notes

- Both skills are idempotent. Re-running this orchestrator with the same inputs adds no duplicate rows.
- If the user already has populated companies in `Companies` from a previous run, those will be skipped at write time but will still flow into Phase C.
