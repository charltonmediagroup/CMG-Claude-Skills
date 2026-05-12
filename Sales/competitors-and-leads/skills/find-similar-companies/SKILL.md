---
name: find-similar-companies
description: Find companies similar to a given company. Generalised, ad-hoc version of /sales-find-competitors — takes any company name + a free-text description of what kind of company it is (e.g. "B2B retail SaaS", "fintech payments", "regional airline"), optional region (default Global), and an optional max count. Claude WebSearches and returns 5–10 verifiable similar companies with name, industry, website, and a one-sentence reason. Appends to the 'Companies' tab of the ad-hoc Google Sheet (1NpFZ2J...). Use when the user asks to find similar companies, find competitors of a specific company, /find-similar-companies, or wants a one-off lookup that's NOT tied to the SBR client list.
---

# /find-similar-companies

Ad-hoc, one-shot version of `/sales-find-competitors`. Takes a single company + free-text category from the user and finds similar/competitor companies anywhere in the world (or in a region the user specifies).

**Not tied to the SBR client sheet** — results land in a separate ad-hoc Google Sheet (`1NpFZ2JdtZQqgWHyp5tL2uAsQJWdEWE9uvLr1OyuNiqg`) under the `Companies` tab. The first run on a fresh tab auto-bootstraps the column headers; you do not need to set them by hand.

## Where the code lives

`~/.claude/competitors-and-leads/` — same bundle as the rest of the sales skills. The CLI entrypoint is `run.py`, the module is `lib/adhoc_competitors.py`, and the writer is `lib/adhoc_writers.py`.

## Inputs you need from the user

If the user didn't already provide them, ask for:
1. **Company name** — the source company they want similar companies for.
2. **What kind of company is it?** — free-text. Examples: "B2B SaaS for retail", "regional low-cost airline", "Singaporean fintech payments processor", "Japanese consumer electronics conglomerate". The richer this is, the better the matches.
3. *(Optional)* **Region** — e.g. `APAC`, `Singapore`, `EMEA`, `North America`. Default: `Global` (no geographic filter).
4. *(Optional)* **Max count** — how many similar companies to find. Default: 10.

## Runbook

### Step 1 — Stage the context

```
python ~/.claude/competitors-and-leads/run.py adhoc-similar-collect \
  --company "<company name>" --kind "<kind>" \
  [--region "<region>"] [--max <N>]
```

Writes `~/.claude/competitors-and-leads/output/adhoc_similar_context.json` with the user's input — no API calls yet, since you (Claude) do the searching.

### Step 2 — Reasoning (you, Claude, do this)

Run **at most 2 WebSearch calls** to identify similar companies. Apply the rules in `~/.claude/competitors-and-leads/lib/prompts.py` (`ADHOC_SIMILAR_SYSTEM` + `ADHOC_SIMILAR_USER_TEMPLATE`):

- N similar companies (where N = the user's `--max`, default 10).
- Real, verifiable companies only — no fabrication.
- Match by what kind of company the source actually is, not just superficial keywords.
- Each entry: `similar_company_name`, `industry`, `website` (must be real), `why_similar` (one sentence).

Suggested search queries:
- `"<company>" similar companies <kind>`
- `"<company>" competitors OR alternatives <region if any>`

Use `WebFetch` only if a candidate's existence needs sanity-checking (rare for well-known companies).

Save the merged result to `~/.claude/competitors-and-leads/output/adhoc_similar_drafts.json`:

```json
{
  "companies": [
    {
      "Source Company": "<the company the user asked about>",
      "Source Company Kind": "<the kind they typed>",
      "Region": "<region or 'Global'>",
      "Similar Company Name": "...",
      "Industry": "...",
      "Website URL": "https://...",
      "Why Similar": "One-sentence reason.",
      "Generated At": "<today's ISO date>",
      "Status": "new"
    }
  ]
}
```

The `Generated At` field can be copied from the `generated_at` value in the context JSON written by Step 1.

### Step 3 — Show your work and ask before writing

Print a tally + a short table (Similar Company / Industry / Website / Why Similar). Ask the user to confirm before writing to the sheet.

### Step 4 — Write to the sheet

```
python ~/.claude/competitors-and-leads/run.py adhoc-similar-write \
  --input ~/.claude/competitors-and-leads/output/adhoc_similar_drafts.json
```

Appends new rows to the `Companies` tab in the ad-hoc sheet. Idempotent — rows already present (matched on `Source Company` + `Similar Company Name`, lowercased) are skipped. Bootstraps the header row on the first run.

## Composability

The output of this skill feeds directly into `/find-company-pocs`. After this writes, you can hand the same `adhoc_similar_drafts.json` (re-shaped to `[{"name":..., "website":..., "source_company":...}]`) to the POC skill, or use the combined `/find-similar-companies-and-pocs` to do both in one go.

## Verification

After writing, open the sheet and confirm: rows landed in the `Companies` tab with all 9 columns populated, `Status='new'`, and the `Source Company` field matches what the user asked about.

## Notes

- If the service-account email doesn't have Editor access to the ad-hoc sheet, the write will fail. The SA email is in `gsheets-sa.json` (`client_email` field) — share the sheet with it.
- This skill does NOT touch the existing SBR/Competitors/POCs/Email Drafts tabs. It's a separate workflow.
- If WebSearch returns nothing useful, return an empty array rather than fabricating companies.
