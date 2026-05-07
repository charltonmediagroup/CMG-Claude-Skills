# TDM-EMR — Travel Daily Media Earned Media Report

Workspace for `/earned-media-report` — generates an Earned Media Report DOCX for any hospitality / travel brand by scraping Travel Daily Media (TDM) and rendering the result against the Minor Hotels reference report.

For Charlton Media's five B2B publications (SBR, HKB, ABF, ABR, RA) use the sister workspace at [`../EMR/`](../EMR/README.md) instead.

## What's here

- `Minor Hotels — Earned Media Report.pdf` — the reference report. Structure and tone for new reports should match this.
- `Media Kit.pdf` — TDM's product catalog (prices, deliverables, events). **Required for the Recommendations section.** SKILL.md Step 4.5 opens this file via `Read` (or `anthropic-skills:pdf-reader`) and the Recommendations section names products and prices from it. Without the file, the report still renders, but Recommendations will be generic and won't quote any prices. Gitignored (licensed catalog) — source it from the team's internal Drive and replace whenever pricing or products change.
- `scripts/earned-media-report.mjs` — Node helper that scrapes TDM, parses each article's JSON-LD, applies a brand-keyword filter, and writes a JSON dataset.
- `.claude/skills/earned-media-report/SKILL.md` — runbook Claude follows when you invoke the skill.
- `output/earned-media/` — generated DOCX reports (auto-created, gitignored). Intermediate JSON is cached in `output/earned-media/.cache/` and re-used on subsequent runs of the same brand to skip re-scraping.

## Requirements

- **Node.js 18+** on PATH (built-in `fetch` requires v18).
- **Claude Code** opened with this folder as the working directory.

No `npm install` required — the helper has zero dependencies.

## Usage

From the TDM-EMR folder:

```bash
cd "C:\Users\USER\Desktop\CMG Claude Skills\TDM-EMR"
claude
```

Then in Claude Code:

```
/earned-media-report Hilton
```

(or any brand name)

Claude will:

1. Propose a sub-brand keyword list and ask you to approve it.
2. Run the scrape helper.
3. Flag borderline articles (roundups, passing mentions) for you to confirm exclusions.
4. Read the Media Kit so the Recommendations section names specific TDM products.
5. Draft the report content in first-person voice ("we", "our").
6. Render it to DOCX.

The final DOCX lands in `output/earned-media/<brand-slug>.docx`. An HTML version also lands alongside it as a quick-inspection artifact.

## Running the helper directly

If you want to run just the scrape step without the skill (e.g., to inspect raw data):

```bash
node scripts/earned-media-report.mjs \
  --brand "Minor Hotels" \
  --keywords "Minor Hotels,Anantara,Avani,Tivoli,NH,Oaks,nhow,Colbert Collection,Wolseley,Elewana"
```

Outputs (in the hidden cache subfolder so they don't clutter the visible deliverable folder):

- `output/earned-media/.cache/<slug>-raw.json` — every article from the search, including filtered-out ones, with `kept`/`dropReason` flags.
- `output/earned-media/.cache/<slug>-filtered.json` — kept articles only, sorted newest-first.

Optional flags: `--rate-ms`, `--concurrency`, `--max-body-chars`, `--max-pages`. See `node scripts/earned-media-report.mjs --help`.

## How the filter works

An article is kept only if **at least one brand keyword appears in the title or in the first ~350 characters of body text**. This catches the case the original Minor Hotels run flagged: TDM's site search returns articles where the brand is mentioned only in passing (multi-brand roundups, partner platform stories, coalition pieces), and those should not count toward Earned Media Value.

The keyword list is the parent brand plus every sub-brand. Two-letter tokens like `NH` use plain substring matching, so the manual review step in the skill exists to catch the rare false positive.
