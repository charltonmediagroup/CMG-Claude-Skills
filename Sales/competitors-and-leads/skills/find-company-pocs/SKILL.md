---
name: find-company-pocs
description: Find POCs (points of contact) at one or more given companies, filtered by USER-SPECIFIED job titles. Generalised, ad-hoc version of /sales-find-pocs — not hardcoded to marketing/comms. The user supplies the target companies (name + website) plus the kind of role they want (casual phrasing OK — "sales leaders", "engineering managers", "HR Director") and an optional region. Claude expands the casual title input into a moderate list of LinkedIn-style title variants (synonyms + adjacent seniority levels in the same function — e.g. "sales leaders" → "VP Sales, Vice President Sales, Sales Director, Director of Sales, Head of Sales, CRO, Chief Revenue Officer"), confirms the expanded list with the user, then hits Tavily (LinkedIn URL + team page + contacts), Apify (LinkedIn employees + profiles with email search) using the expanded titles + region as filters, and Hunter.io (domain emails, no department filter). Claude post-filters results to match the requested titles. Appends to the 'POC' tab of the ad-hoc Google Sheet (1NpFZ2J...). Use when the user asks to find POCs at specific companies, find people with specific titles at a company, /find-company-pocs, or wants to extend /find-similar-companies output into actual contacts.
---

# /find-company-pocs

Ad-hoc, one-shot version of `/sales-find-pocs`. Takes a list of target companies + a list of sought job titles + an optional region, and returns matching POCs. Unlike `/sales-find-pocs`, the title filter is **user-supplied** — you can ask for VP Sales, CTOs, HR Directors, anything.

Results land in the `POC` tab of the ad-hoc Google Sheet (`1NpFZ2JdtZQqgWHyp5tL2uAsQJWdEWE9uvLr1OyuNiqg`). The first run on a fresh tab auto-bootstraps the column headers.

## Inputs you need from the user

1. **Target companies** — name + website per company. Either:
   - The user provides them inline, OR
   - The user just ran `/find-similar-companies`, in which case use the rows from `~/.claude/competitors-and-leads/output/adhoc_similar_drafts.json` (mapping `Similar Company Name` → `name`, `Website URL` → `website`, and `Source Company` → `source_company`).
2. **Sought job titles** — casual input is fine. The user can say `"sales leaders"`, `"engineering managers and above"`, `"HR"`, or already-formatted lists like `"VP Sales, Sales Director"`. You expand it in Step 1 below.
3. *(Optional)* **Region** — e.g. `APAC`, `Singapore`, `EMEA`. Default: `Global` (no geographic filter).

## Runbook

### Step 1 — Expand the sought job titles (REQUIRED, do this first)

The user's job titles are passed straight to Apify's `jobTitles` filter, which does **literal substring matching** on LinkedIn titles. So `"VP Sales"` won't match `"Vice President Sales"` and `"CTO"` won't match `"Chief Technology Officer"` — they're different strings to Apify. To avoid missing real POCs, expand the user's input into a comma-separated list of literal title variants BEFORE running the collect step.

**Use moderate expansion**: include direct synonyms PLUS adjacent seniority levels within the same function. Do NOT include lateral or unrelated roles.

| User said | Expanded list (paste this into `--titles`) |
|---|---|
| `sales leaders` / `VP Sales` | `VP Sales, Vice President Sales, Sales Director, Director of Sales, Head of Sales, Chief Revenue Officer, CRO, Senior Sales Director` |
| `senior engineers` / `Engineering Manager` | `Engineering Manager, Senior Engineering Manager, Director of Engineering, Engineering Director, Head of Engineering, VP Engineering, Vice President Engineering, CTO, Chief Technology Officer` |
| `HR` / `HR Director` | `HR Director, Director of HR, Head of HR, VP People, VP HR, Chief People Officer, CPO, People Operations Lead, HR Manager` |
| `CTO` | `CTO, Chief Technology Officer, VP Engineering, Vice President Engineering, Head of Engineering` |
| `marketing leaders` | `Marketing Director, Director of Marketing, Head of Marketing, VP Marketing, Vice President Marketing, CMO, Chief Marketing Officer, Senior Marketing Manager, Marketing Manager` |

**Rules of moderate expansion:**
- Always include both abbreviation AND spelled-out form (`CTO` and `Chief Technology Officer`, `VP X` and `Vice President X`).
- Always include the synonym variant (`Sales Director` and `Director of Sales`, `Head of X` and `VP X`).
- Include one tier up and one tier down within the same function (Engineering Manager → also Senior Engineering Manager and Director of Engineering).
- Do NOT include unrelated functions even if titles sound similar (don't add `Account Director` when user asked for `Sales Director` — different role).
- Do NOT include individual contributors when the user clearly meant leadership (don't add `Sales Representative` for `Sales Director`).

**Step 1b — Pick Hunter.io departments to match the function.** Hunter's free tier caps results at 10 emails per call. To make those 10 count, filter Hunter server-side to the department(s) closest to what the user is asking for. Hunter's department parameter accepts only these 14 fixed values:

`executive, it, finance, management, sales, legal, support, hr, marketing, communication, education, design, health, operations`

Map the user's intent to 1–4 of those. Examples:

| User function | Hunter departments |
|---|---|
| Sales / Revenue / Account leadership | `sales, executive, management` |
| Engineering / IT / DevOps / Tech leadership | `it, executive` |
| HR / People Ops | `hr, management` |
| Finance / CFO / Controller | `finance, executive, management` |
| Marketing / Demand Gen / Growth | `marketing, management` |
| PR / Communications | `communication, marketing` |
| Operations / COO | `operations, management, executive` |
| Legal / Compliance | `legal, management` |
| Customer Success / Support | `support` |
| Design / UX | `design` |
| C-suite (any) | `executive` |
| Spans many functions or no clean fit (e.g. underwriters) | omit — leave unfiltered |

**Step 1c — Show both the expanded titles and the Hunter departments to the user, ask them to confirm or edit either.** Example phrasing:

> "I'll search with these:
>
> **Apify / Tavily titles** (full list — Apify gets all, Tavily gets the first 3):
> `VP Sales, Vice President Sales, Sales Director, Director of Sales, Head of Sales, Chief Revenue Officer, CRO, Senior Sales Director`
>
> **Hunter.io departments** (free-tier 10-email cap will be filtered to these):
> `sales, executive, management`
>
> OK to proceed, or want to add/remove anything?"

Wait for confirmation. Carry the confirmed values forward as `<EXPANDED_TITLES>` and `<HUNTER_DEPTS>` for the steps below.

### Step 2 — Build the input file

Hand-write `~/.claude/competitors-and-leads/output/adhoc_pocs_input.json`:

```json
[
  {"name": "Notion", "website": "notion.so", "source_company": "Notion"},
  {"name": "Coda",   "website": "coda.io",   "source_company": "Notion"}
]
```

`source_company` is optional — defaults to `name` when missing. It's only meaningful when the targets came from `/find-similar-companies` (so each POC row remembers which originally-asked-about company it traces back to).

### Step 3 — Dry-run candidate count

```
python ~/.claude/competitors-and-leads/run.py adhoc-pocs-collect \
  --input ~/.claude/competitors-and-leads/output/adhoc_pocs_input.json \
  --titles "<EXPANDED_TITLES from Step 1>" \
  [--hunter-depts "<HUNTER_DEPTS from Step 1>"] \
  [--region "<region>"] \
  --dry-run
```

This is the highest-cost step: each target company fires ~6 API calls (Tavily ×3, Apify ×2, Hunter ×1). Apify can take up to 2 minutes per company. **Always confirm with the user before doing >5 candidates.**

### Step 4 — Collect raw research

```
python ~/.claude/competitors-and-leads/run.py adhoc-pocs-collect \
  --input ~/.claude/competitors-and-leads/output/adhoc_pocs_input.json \
  --titles "<EXPANDED_TITLES from Step 1>" \
  [--hunter-depts "<HUNTER_DEPTS from Step 1>"] \
  [--region "<region>"]
```

Writes `~/.claude/competitors-and-leads/output/adhoc_pocs_context.json`. Each candidate block contains: `linkedin_company_url`, `apify_employees`, `apify_profiles`, `team_page_search`, `contacts_search`, `hunter_emails`, `skipped_reason`.

How each tool uses the title/department info:

- **Apify** — full `<EXPANDED_TITLES>` list goes into `jobTitles` (server-side filter on LinkedIn current title).
- **Tavily contacts query** — first 3 titles only, baked into the search string; more keywords degrade search quality.
- **Tavily team-page query, Tavily LinkedIn-URL lookup, Apify profile enrichment** — don't use titles at all.
- **Hunter.io** — uses `<HUNTER_DEPTS>` if provided (server-side filter to those depts, `limit=10` free-tier cap). If `--hunter-depts` is omitted, Hunter is unfiltered and Claude post-filters from the raw 10. Filtering is recommended whenever the user's intent maps cleanly to Hunter's 14 fixed departments.

### Step 5 — Reasoning (you, Claude)

For each candidate block, apply `ADHOC_POCS_EXTRACT_USER_TEMPLATE` from `~/.claude/competitors-and-leads/lib/prompts.py`. Substitute `{target_company}`, `{sought_titles}`, and `{all_content}` (concatenation of Tavily team-page summaries, Tavily contacts summaries, Apify employee headlines, and Hunter emails).

Match generously — a "Director of Revenue" matches "Sales Director", "Head of Engineering" matches "VP Engineering", etc. Use judgment. If the title is clearly orthogonal (e.g. user asked for "VP Sales" and the candidate is "Marketing Specialist"), exclude.

The Apify path already returns structured POC data (`firstName`, `lastName`, `headline`, `experience`, `linkedinUrl`); the AI extraction is the catch-all for cases where Tavily/Hunter found people Apify missed.

Merge sources, dedupe by full name (lowercased), prefer rows with a real email over `email not found`. Final POC schema (matches the `POC` tab):

```json
{
  "Source Company": "<from input.source_company, defaults to Target Company Name>",
  "Target Company Name": "...",
  "Target Company Website": "...",
  "Sought Job Titles": "<the EXPANDED title list from Step 1, comma-joined>",
  "POC Full Name": "...",
  "Job Title": "...",
  "Email": "<email or 'email not found'>",
  "LinkedIn URL": "...",
  "Location": "...",
  "Other Contact Info": "<e.g. phone>",
  "Status": "new",
  "Research Sources": "<\\n-separated list of source URLs>",
  "Enrichment Source": "Apify/LinkedIn, Tavily/AI, Hunter.io",
  "Generated At": "<today's ISO date>"
}
```

Save merged output to `~/.claude/competitors-and-leads/output/adhoc_pocs_drafts.json`:

```json
{ "pocs": [{...}] }
```

For batches over 5 candidates, delegate per-target extraction to Explore subagents in parallel.

### Step 6 — Show your work + write

Print per-target POC counts. Ask the user to confirm. Then:

```
python ~/.claude/competitors-and-leads/run.py adhoc-pocs-write \
  --input ~/.claude/competitors-and-leads/output/adhoc_pocs_drafts.json
```

Appends new POC rows to the `POC` tab. Idempotent on `(Target Company Name, POC Full Name)` lowercased — re-running won't duplicate. Bootstraps the header row on the first run.

## Verification

Open the sheet, check the `POC` tab. Rows should have all 14 columns populated, `Status='new'`, the `Sought Job Titles` field matches what the user asked for, and the `Job Title` column contains roles that actually match (or are functionally equivalent to) the sought titles.

## Notes

- If a target company has no findable LinkedIn company URL, the Apify steps are skipped and extraction works only off Tavily team-page + contacts results + Hunter emails.
- Hunter is called with `limit=10` (the free-tier cap) and the department(s) you confirmed in Step 1b. If you skipped that selection (e.g. the user's titles don't fit Hunter's 14 fixed departments), Hunter is queried unfiltered and Claude post-filters from the raw 10. Hunter's 14 valid department codes: `executive, it, finance, management, sales, legal, support, hr, marketing, communication, education, design, health, operations`. Passing anything outside that list errors out before any API call. If you're on a paid Hunter plan, bump the `limit=10` in `lib/adhoc_pocs.py` for a wider pool.
- If Apify returns zero matches for the user's titles, that's a real signal — the company may not have those roles publicly listed. Flag in the per-target tally.
- Service-account email needs Editor access to the ad-hoc sheet (`1NpFZ2J...`). Share with the SA email from `gsheets-sa.json`'s `client_email`.
