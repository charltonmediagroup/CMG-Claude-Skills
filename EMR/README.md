# EMR — Charlton B2B Earned Media Reports

Self-contained workspace for generating Earned Media Report DOCX deliverables from five Charlton Media B2B publications. EMV is a flat USD 1,800 per piece. Reports can target a single publication (per-pub DOCX, "we at <pub>" voice) or a combination of publications (one combined master DOCX, neutral third-person voice). Recommendations sections were removed; reports stop at the Article Inventory.

## Publications

| Acronym | Domain | Publication name |
|---|---|---|
| SBR | sbr.com.sg | Singapore Business Review |
| HKB | hongkongbusiness.hk | Hong Kong Business |
| ABF | asianbankingandfinance.net | Asian Banking & Finance |
| ABR | asianbusinessreview.com | Asian Business Review |
| RA  | retailasia.com | Retail Asia |

## What's here

```
EMR/                                       ← run claude from this folder
  Minor Hotels — Earned Media Report.pdf   ← reference report; SKILL.md links to it for tone/length anchors
  thought-leader-package-prices.md         ← historical reference only; the skill no longer reads it
  SBR Media Kit.pdf, HKB Media Kit.pdf, ABF Media Kit.pdf,
  ABR Media Kit.pdf, RA Media Kit.pdf      ← reference only (image-only PDFs; not parsed at runtime)
  scripts/
    charlton-emr.mjs                       ← Drupal-sitemap scraper (Node 18+, no deps); called once per pub per run
    render-docx.py                         ← legacy single-pub DOCX renderer (python-docx); the skill now renders
                                             via anthropic-skills:docx instead
  output/
    <ACRONYM>/                             ← one folder per publication
      <brand-slug>.docx                    ← single-pub deliverable
      .cache/
        <brand-slug>-raw.json              ← all URLs with kept/dropReason
        <brand-slug>-filtered.json         ← kept-only, newest-first (single source of truth for content)
        <brand-slug>-curated.json          ← post-QA dataset (after manual exclusions)
        <brand-slug>-content.json          ← composed report content (Exec Summary, Observations…)
        <brand-slug>-aggregates.json       ← year/category/sector aggregations
        <brand-slug>-drops.json            ← audit log of articles excluded at QA
    COMBINED/                              ← combined-mode output folder
      <brand-slug>.docx                    ← combined master DOCX (2+ pubs)
  .claude/
    skills/charlton-earned-media-report/
      SKILL.md                             ← runbook Claude Code discovers when invoked from this folder
```

## Usage

From this folder:

```
cd "C:\Users\USER\Desktop\EMR"
claude
```

Then in Claude Code, pick the invocation form that matches your scope:

```
# Single publication → output/<ACRONYM>/<brand-slug>.docx
/charlton-earned-media-report SBR DBS

# Specific subset of publications → output/COMBINED/<brand-slug>.docx
/charlton-earned-media-report SBR,HKB,ABF DBS

# All five publications → output/COMBINED/<brand-slug>.docx
/charlton-earned-media-report DBS
```

Acronyms are case-insensitive; the publication list is comma-separated **with no spaces** (`SBR,HKB`, not `SBR, HKB`). Replace `DBS` with any brand. Claude will:

1. Parse the arguments to resolve which publications to run and the brand. Single acronym → single-pub mode; comma-list of acronyms → combined mode with those pubs; no acronym → combined mode with all five.
2. Propose a brand + sub-brand keyword list and ask you to approve it once for the whole run.
3. Run the scraper sequentially, once per selected publication. If a publication's scrape fails, log it and continue with the rest.
4. Flag borderline articles (industry roundups, analyst-attribution pieces, daily-markets briefings, regulator notices, slug false positives) across every selected pub and ask you for one combined approval.
5. Draft the report content. Single-pub mode uses "we at <publication>" voice; combined mode uses neutral third person and lists every selected pub in the `Prepared by:` line.
6. Render it to `output/<ACRONYM>/<brand-slug>.docx` (single-pub) or `output/COMBINED/<brand-slug>.docx` (combined).
7. Surface any failed publications at the end so you know what's missing.

## Running the scraper directly

```bash
node scripts/charlton-emr.mjs \
  --site SBR \
  --brand "DBS" \
  --keywords "DBS,POSB,Vickers,Treasures,DBS Bank,DBS Group,DBS Private Bank,DBS Foundation"
```

Outputs land in `output/SBR/.cache/`. See `--help` for tuning flags (`--rate-ms`, `--concurrency`, `--max-body-chars`, `--max-sitemap-pages`).

## How the filter works

Two-stage filter to keep runs feasible against Drupal sitemaps with tens of thousands of URLs:

1. **URL pre-filter (cheap, before any article fetches):**
   - Drop any URL matching `/<section>/sponsored-articles/<slug>` — sponsored articles are paid placement, not earned coverage.
   - Keep only URLs whose **slug** contains a brand keyword (kebab-cased, 1:1 with each entry in the keyword list — no token splitting).
2. **Title + body keyword filter (after fetch):** an article is kept only if at least one keyword appears in the title or first ~350 characters of body text.

**Coverage tradeoff:** an article that mentions the brand only in body text — not in slug or title — will be missed. For Tier-1 B2B brands (DBS, HSBC, OCBC, Watsons, etc.) the brand is virtually always in the slug of any article *about* it. For lower-coverage brands, expand the keyword list (nicknames, ticker symbols, parent-company variants) before running.

**Keyword-matcher rule (1:1):** each keyword maps to exactly one slug matcher. Multi-word keywords like `"DBS Bank"` match the kebab `dbs-bank` only — not the bare tokens. If you want a slug containing only `vickers` (no `dbs` prefix) to match, list `"Vickers"` as its own keyword. Generic English nouns (`bank`, `group`, `private`, `holdings`, `foundation`) are bad standalone keywords — they degrade slug-filter into a sector-wide net.

**Multi-pub runs reuse the keyword list.** A combined run approves the keyword list once and passes the same list to every scrape (one scraper invocation per selected publication). Brand sub-entities don't change between pubs, so per-pub re-prompting would just add friction.

## Requirements

- **Node.js 18+** on PATH (built-in `fetch` requires v18). No `npm install` — zero dependencies on the scraper.
- **Python 3** with `python-docx` only if you want to use the legacy `scripts/render-docx.py` standalone — the skill itself renders via `anthropic-skills:docx`, which has no Python dependency.
- **Claude Code** opened with this `EMR` folder as the working directory.
