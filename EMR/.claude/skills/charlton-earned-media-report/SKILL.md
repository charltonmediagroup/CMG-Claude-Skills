---
name: charlton-earned-media-report
description: Generate an Earned Media Report DOCX for a brand by scraping one or more Charlton Media B2B publications. Supports five publications by acronym — SBR (Singapore Business Review), HKB (Hong Kong Business), ABF (Asian Banking & Finance), ABR (Asian Business Review), RA (Retail Asia). Walks each site's Drupal sitemap, drops sponsored articles, applies a brand-keyword filter, and renders a DOCX. Three invocation forms — `/charlton-earned-media-report <brand>` runs all five publications and produces one combined master DOCX; `/charlton-earned-media-report <ACRONYM1,ACRONYM2,...> <brand>` runs the listed publications and produces one combined master DOCX; `/charlton-earned-media-report <ACRONYM> <brand>` runs a single publication and produces a per-publication DOCX. Use when the user asks to "produce an earned media report" for a brand on one or more of these publications, or asks to replicate the Minor Hotels report format for a B2B brand.
---

# Charlton B2B Earned Media Report

You are helping the user produce a polished DOCX Earned Media Report on the brand they name, sourced from **one or more** of five Charlton Media B2B publications. The reference structure is in [Minor Hotels — Earned Media Report.pdf](../../../Minor%20Hotels%20—%20Earned%20Media%20Report.pdf) — match its sections, tone, and table layout, with the modifications described below for combined (multi-publication) reports.

The mechanical scraping is done by `scripts/charlton-emr.mjs` (Node 18+, no dependencies). It walks one publication's Drupal sitemap per invocation, drops sponsored URLs by pattern, keeps URLs whose slug contains a brand keyword, fetches them, parses JSON-LD, and applies a title+body keyword filter. The skill calls it once per selected publication. Your job is the judgment work around it: argument parsing, keyword proposal, borderline-case review, narrative writing, and DOCX rendering.

## Site map

| Acronym | Domain | Publication name | "We" voice |
|---|---|---|---|
| SBR | sbr.com.sg | Singapore Business Review | "We at Singapore Business Review…" |
| HKB | hongkongbusiness.hk | Hong Kong Business | "We at Hong Kong Business…" |
| ABF | asianbankingandfinance.net | Asian Banking & Finance | "We at Asian Banking & Finance…" |
| ABR | asianbusinessreview.com | Asian Business Review | "We at Asian Business Review…" |
| RA  | retailasia.com | Retail Asia | "We at Retail Asia…" |

## Workflow

### 0. Resolve the sites and mode

The user can invoke the skill in three ways:

1. `/charlton-earned-media-report <Brand>` — no acronym → use **all five** publications (SBR + HKB + ABF + ABR + RA).
2. `/charlton-earned-media-report <ACRONYM1,ACRONYM2,...> <Brand>` — comma-separated acronym list, no spaces inside the list → use only the listed publications.
3. `/charlton-earned-media-report <ACRONYM> <Brand>` — single acronym → existing single-publication behaviour.

**Parser rule.** Tokenise the arguments by whitespace. Take the **first token** and test:

- If the first token equals one of `SBR / HKB / ABF / ABR / RA` (case-insensitive) → single-pub mode; the rest of the args is the brand.
- Else if the first token is a comma-separated list where **every** element is a valid acronym (e.g. `SBR,HKB`, `sbr,abf,ra`) → multi-pub mode with those pubs; the rest of the args is the brand.
- Else → multi-pub mode with **all five** pubs; the entire args string is the brand.

If a comma-list contains any unrecognised acronym, **stop** and ask the user to fix the list. Do not silently drop unknown entries.

**Mode routing.** The number of resolved publications determines the rest of the workflow:

| Selected pubs | Mode | Output path | Voice in prose | `Prepared by:` line |
|---|---|---|---|---|
| 1 | Single-pub | `output/<ACRONYM>/<slug>.docx` | "we at <publication>" (first-person plural) | Single publication name |
| 2+ | Combined | `output/COMBINED/<slug>.docx` | Neutral third person | All selected publications, Oxford-comma list |

The selected list also determines:

- the domain(s) to scrape (one scrape invocation per pub)
- which `output/<ACRONYM>/.cache/` directories the filtered datasets land in
- which publication name(s) appear in the title block

The Media Kit PDFs in this folder (`<ACRONYM> Media Kit.pdf`) are kept for reference only; the skill no longer reads them at runtime.

### 1. Verify Node 18+

Run `node --version`. If it's not installed or below v18, tell the user to install Node.js 18+ from nodejs.org and stop. Built-in `fetch` requires v18.

### 2. Propose the brand-keyword list

The keyword list separates "article about this brand" from "article that mentions this brand in passing." It must include:

- The parent brand name
- Every sub-brand or product brand the group operates
- Listed-entity / holding-company names if different from the consumer brand
- Major co-marketed sister brands

Brand context here is **B2B / finance / retail / HR / commercial property / telecom / aviation / hospitality / energy** — not just hospitality. Sub-brand portfolios in these sectors usually include holding-company names, listed-entity names (`HSBC Holdings`, `Standard Chartered PLC`), wealth-management or product brands (`HSBC Premier`, `OCBC Premier Banking`), and joint-venture brands. Use **WebSearch** to confirm sub-entity portfolios when in doubt.

**Each keyword maps 1:1 to a slug matcher.** The script does *not* split multi-word keywords into bare tokens. If you want a slug like `vickers-asia-rebrand` (no parent prefix) to match, list `"Vickers"` as its own keyword. List the parent brand AND each distinctive sub-brand token separately. Do not include generic English nouns (`bank`, `group`, `private`, `foundation`, `holdings`) as standalone keywords — they would match thousands of unrelated sector slugs and inflate fetch volume. They are fine inside multi-word keywords (`"DBS Bank"` is fine; bare `"Bank"` is not).

Worked example for **DBS**:

- ✅ Good: `"DBS, POSB, Vickers, Treasures, DBS Bank, DBS Group, DBS Private Bank, DBS Foundation"` — `Vickers` and `Treasures` listed as their own tokens to catch slugs that drop the parent prefix; multi-word keywords like `"DBS Bank"` still match the exact `dbs-bank` kebab.
- ❌ Bad: `"DBS, POSB, DBS Vickers, DBS Treasures"` — slugs containing only `vickers` (without a leading `dbs`) won't match.
- ❌ Worse: adding `"Bank"` or `"Group"` as standalone keywords — would match thousands of unrelated finance/sector slugs and silently 5–10× the fetch cost.

Draft the equivalent list, **show it to the user, and get explicit approval or edits before running the scrape.** Do not run the helper with an unconfirmed list.

When you propose the list, briefly explain *why* each entry is included so the user can spot omissions.

**Multi-pub runs:** propose the keyword list **once** and reuse the same approved list across every selected publication. Brand sub-entities don't change between pubs, so a per-pub re-prompt would just add friction. The user only approves once.

### 3. Run the scrape helper (once per selected publication)

Once the keyword list is approved, invoke the scraper **sequentially, once per selected publication**:

```bash
node scripts/charlton-emr.mjs \
  --site <ACRONYM> \
  --brand "<Brand Name>" \
  --keywords "<comma,separated,list>"
```

Each invocation writes to `output/<ACRONYM>/.cache/`:

- `.cache/<slug>-raw.json` — every URL the sitemap returned, with `kept`/`dropReason` flags. Use this for QA — it tells you *why* each article was dropped.
- `.cache/<slug>-filtered.json` — kept articles only, sorted newest-first. This is the dataset for the report.

The script's stdout summary tells you how many sitemap pages were walked, how many sponsored URLs were dropped, how many slugs matched a keyword, and how many passed the title+body filter. **Surface those numbers to the user after each pub**, then move on to the next.

**Run sequentially**, not in parallel — each scrape is rate-limited against the target site, and parallel runs don't share state. Sequential keeps the network behaviour predictable.

**Failure handling.** If a single publication's scrape fails (network error, sitemap timeout, HTTP 5xx), log the error with the pub name and the failing URL/step, and **continue with the next publication**. Don't abort the whole run. Collect all failures into a list and surface them at Step 7 ("These publications failed and are not in the report: …"). The combined report renders only the publications that succeeded.

**Coverage tradeoff to disclose up front:** the scraper only fetches URLs whose **slug** contains a keyword. This keeps runs feasible against sitemaps with tens of thousands of URLs but means an article that mentions the brand only in body text — not in the slug or title — is not in scope. For Tier-1 B2B brands (DBS, HSBC, OCBC, Watsons, etc.), the brand is virtually always in the slug of an article *about* it, so this is usually fine. Tell the user this tradeoff once before the first scrape and confirm they accept it; you don't need to re-confirm per publication.

### 4. Manual QA — flag borderline articles

Read each selected publication's `output/<ACRONYM>/.cache/<slug>-filtered.json`. Scan titles plus URL paths and identify articles that should *probably* be excluded even though they passed both filters. Patterns to flag in B2B coverage:

| Pattern | Why exclude |
|---|---|
| Multi-bank / multi-company industry roundups ("Top 5 Singapore banks…", "Asia's biggest retailers…") | Brand isn't the subject |
| Regulator / watchdog notices listing the brand among many (MAS, HKMA, BSP) | Brand is one of many recipients |
| Index / market-cap / league-table pieces | Brand is one row of dozens |
| Press-release-distribution pieces that re-hash a wire announcement | Often the same content the brand pushed elsewhere |
| Earnings / sector recap roundups covering the whole industry | Brand is one of several recapped |
| Q&A or feature where the brand is mentioned but not the subject | Subject is the interviewee or theme |
| Slug-keyword false positives — slug contains a keyword as a substring of an unrelated word | Mirrors the TDM `NH` matching risk; e.g. a 3-letter ticker matching inside a longer word |

Compile a candidate exclusion list with article URLs and a one-line reason for each. **Show it to the user and get explicit approval before regenerating numbers.** Do not silently drop anything.

**Multi-pub runs.** Compile **one** combined exclusion list grouped by publication (e.g. a section per pub with the candidates underneath). Present it once and get one approval. Don't ask the user to step through publications one at a time.

If the count changes between drafts (e.g., 47 → 41 after exclusions), state both numbers explicitly when you report back. Don't paper over count drift.

### 5. Generate the report content

Compose the report content following the Minor Hotels structure. **Match the prose length of the reference PDF** ([Minor Hotels — Earned Media Report.pdf](../../../Minor%20Hotels%20—%20Earned%20Media%20Report.pdf)) — the goal is calm editorial commentary, not a sales deck. If a paragraph creeps past the targets below, cut it back.

**Recommendations are removed from every report — both single-pub and combined.** Skip the section entirely; do not pull prices from `thought-leader-package-prices.md`. The reports stop at the Article Inventory.

**Voice rule — branch by mode:**

- **Single-pub mode (1 selected publication).** First-person plural. The publication is the speaker. Use *we*, *our*, *us*.
  - ✅ *"We at Singapore Business Review published 47 unique editorial pieces in which DBS or one of its sub-brands is the direct subject."*
  - ✅ *"Our coverage of the group has accelerated noticeably in recent years."*
  - ❌ *"SBR published 47 pieces…"* / *"They covered the group across 47 articles…"*
  - Confirm the "we" matches the single acronym resolved in Step 0.

- **Combined mode (2+ selected publications).** Neutral third person. Name the publications explicitly; never use "we", "our", or "us".
  - ✅ *"Singapore Business Review, Retail Asia, and Asian Banking & Finance together published 47 unique editorial pieces in which DBS or one of its sub-brands is the direct subject."*
  - ✅ *"Coverage of the group has accelerated noticeably across the three titles in recent years."*
  - ❌ *"We at Singapore Business Review, Retail Asia, and Asian Banking & Finance published 47…"* / *"Our combined coverage…"*
  - Never lapse into per-pub first person inside a combined report.

**Length anchors (counted directly from the reference PDF):**

| Section | Target | Shape |
|---|---|---|
| Executive Summary | ~160 words across 2 paragraphs (P1 ~60, P2 ~100) | P1 = scoped intro + EMV figure (3 sentences). P2 = narrative on what drove the count (4 sentences). |
| Strategic Observations | ~185 words across 4 bullets | Each bullet 2–3 sentences (~35–55 words). Open with a bold thesis sentence, then 1–2 supporting sentences. |

#### 5a. Sections in order — single-pub mode

1. **Title block** — `<Brand> — Earned Media Report`, "Prepared by: <Publication name>", period (earliest article date – today's date), date.
2. **Executive Summary** — match the length anchor above. Cover total pieces, EMV, and the narrative of what drove the count (sub-brand mix, standout years, story types). Tailor to what the data shows; don't reuse Minor Hotels phrasing.
3. **Financial Summary** — table with `Total unique editorial pieces`, `Flat media value per piece` (USD 1,800), `Total Earned Media Value` (`pieces × $1,800`), `Coverage window`.
4. **By year** — pieces and EMV per calendar year, ordered ascending, with a Total row.
5. **By category** — pieces and share-% per taxonomy bucket, ordered descending by count. The B2B taxonomy is: `News`, `Features`, `Interviews`, `Appointments`, `Events`, `Exclusives`, `Sectors`. The scraper sets `category` per article from the URL path. The dataset also exposes a `sector` field (commercial-property, financial-services, etc.) — useful for Strategic Observations, but don't double-table it.
6. **Strategic Observations** — 4 bullets matching the length anchor above. Cover: dominant theme, trend over time, dominant sub-brand(s), gaps in higher-value editorial formats. Be specific — name properties, deals, executives where the dataset supports it.
7. **Article Inventory** — full table, newest-first, columns: `#`, `Date`, `Article` (hyperlinked title using the **canonical URL from the dataset**), `Category`. EMV is implicit (every row = $1,800).

#### 5b. Sections in order — combined mode

For combined mode, **merge the per-pub `<slug>-filtered.json` datasets in memory** into a single working dataset, attributing each article to its source publication via a `publication` field. Aggregate from there.

1. **Title block** — `<Brand> — Earned Media Report`. `Prepared by:` lists every selected publication by full name with Oxford-comma separation, e.g. `Prepared by: Singapore Business Review, Retail Asia, and Asian Banking & Finance`. Period = earliest article date across all pubs → today's date. Date = today.
2. **Executive Summary** — neutral third person, ~160 words across 2 paragraphs. Mention the selected publications by name. Cover cross-pub totals (pieces, EMV) and the narrative of what drove the count (which pubs led on which sub-brands, standout years, story types).
3. **Financial Summary** — same table as single-pub. `Total unique editorial pieces` = cross-pub sum. `Total EMV` = cross-pub sum × USD 1,800. `Coverage window` = earliest article date across all pubs → latest article date across all pubs.
4. **By publication** *(new in combined mode)* — table with columns `Publication | Pieces | EMV (USD)`. One row per selected publication ordered by piece count descending. Final Total row sums to the same number as Financial Summary.
5. **By year** — single cross-pub table summing pieces and EMV across every selected publication. Same columns as single-pub: `Year | Pieces | EMV (USD)`, ordered ascending, with a Total row.
6. **By category** — single cross-pub table summing share-% across every selected publication. Same columns and taxonomy as single-pub.
7. **Strategic Observations** — 4 bullets, neutral third person, ~185 words. Bullets can call out per-pub patterns (e.g. *"Hong Kong Business carried the bulk of the wealth-management coverage; Asian Banking & Finance led on regulatory pieces"*) — that's a feature of combined mode, not a deviation.
8. **Article Inventory** — **grouped by publication**. Order pubs by piece count descending. For each pub:
   - A Heading 3 of the form `<Publication name> — N pieces` (e.g. `Singapore Business Review — 22 pieces`).
   - A newest-first table with columns `# | Date | Article (hyperlinked) | Category`. The `#` column resets per pub; do not maintain a global counter.
   - Use the canonical URL from that pub's filtered.json — never reconstruct a URL.

**Critical rules (both modes):**

- **Pull URLs from the dataset only.** Never reconstruct a URL from a title slug. If a URL is missing, leave the title un-linked rather than guessing.
- **Sanity-check the totals before delivering.** In single-pub mode: sum of `By year` pieces == sum of `By category` pieces == length of inventory. In combined mode: also `By publication` total == sum of `By year` pieces == sum of `By category` pieces == sum of all per-pub inventory lengths.
- **EMV is always `pieces × $1,800`.** Don't introduce per-article variation. Don't currency-convert (the EMV is denominated in USD by design).
- **Typography.** Body text and table cells: 11pt. Heading 1 and Heading 2: 14pt. Heading 3 (combined-mode inventory subheaders): 12pt bold.
- **Combined-mode voice discipline.** Grep your draft for `\bwe\b`, `\bour\b`, `\bus\b` before delivering — there should be no first-person plural in a combined report.

### 6. Render the DOCX

**Path branching:**

- **Single-pub mode.** Read `output/<ACRONYM>/.cache/<slug>-filtered.json`. Render to `output/<ACRONYM>/<slug>.docx`.
- **Combined mode.** Read each selected publication's `output/<ACRONYM>/.cache/<slug>-filtered.json` and merge them in memory using the rules in Step 5b. Render to `output/COMBINED/<slug>.docx`. Create the `output/COMBINED/` folder if it doesn't exist. There is no separate combined cache directory — the per-pub `.cache/` files are the single source of truth, and the combined dataset is derived at render time.

Use the `anthropic-skills:docx` skill to produce the DOCX from the content you composed in Step 5. Pass the report as Word-native structures: paragraphs, headings (Heading 1 / Heading 2 / Heading 3 styles), tables, hyperlinks. Match the typography rules:

- Body paragraphs and table cells: **11pt**.
- Heading 1 and Heading 2: **14pt**.
- Heading 3 (combined-mode inventory subheaders): **12pt bold**.

**Output only the DOCX.** The visible `output/<ACRONYM>/` (or `output/COMBINED/`) folder should contain only `<slug>.docx` files (plus the hidden `.cache/` subfolder for per-pub folders).

If the user wants to tweak something after seeing the DOCX, update the content and re-render — don't hand-edit the DOCX in place.

### 7. Final check

Before declaring done, confirm to the user:

**Both modes:**

- Brand and selected publication(s) — explicitly, e.g. "DBS / SBR / Singapore Business Review" (single-pub) or "DBS / SBR + HKB + ABF / Singapore Business Review, Hong Kong Business, and Asian Banking & Finance" (combined).
- Total article count (and any change from earlier drafts).
- Total EMV.
- Path to the DOCX (`output/<ACRONYM>/<slug>.docx` for single-pub, `output/COMBINED/<slug>.docx` for combined).
- Every URL in the inventory was pulled from the canonical link tag (not reconstructed).
- The report contains no Recommendations section.

**Single-pub mode only:**

- Title block reads `Prepared by: <publication name>` and the narrative voice is "we at <publication name>" throughout.

**Combined mode only:**

- Title block's `Prepared by:` line lists every successfully scraped publication, Oxford-comma separated.
- The body voice is neutral third person — no "we", "our", or "us" appears anywhere in the prose.
- The "By publication" table sums to the same total as Financial Summary, By year, and By category.
- The Article Inventory is grouped by publication, ordered by piece count descending.
- If any publication failed during scraping, surface the failures explicitly: "These publications were not included because their scrape failed: <list with one-line reason each>." A combined report with N − 1 pubs is still valid; just be clear about what's missing.

## Anti-patterns

These mistakes happened in the original Minor Hotels run on TDM. Don't repeat them on the Charlton B2B sites:

1. **Fabricating URLs.** When asked for an article link, the previous run reconstructed one from the title slug. Always pull URLs from `.cache/<slug>-filtered.json`.
2. **Silently dropping articles between drafts.** When the filter or exclusion list tightens, the count changes — surface that explicitly.
3. **Treating passing mentions as subject coverage.** The keyword filter automates this on title + first 350 chars of body. The manual QA pass exists because the filter alone misses roundups that *do* mention the brand within the first paragraph.
4. **Two-letter / three-letter token false positives.** Keywords like `NH` or short tickers can match unrelated words. When you scan the dataset, look for any retained article where the keyword appears only as part of a different word and propose it for exclusion.

Charlton-B2B-specific anti-patterns:

5. **Treating sponsored URLs as earned coverage.** The scraper drops `/sponsored-articles/` URLs by URL pattern. If a sponsored piece ever sneaks through (e.g. older URL scheme), drop it manually — it's paid placement, not earned. Sanity-check by grepping the inventory for `sponsored` before delivering.
6. **Slug-only filter blind-spot.** Disclose to the user in Step 3 that the scope is sitemap URLs whose slug contains a keyword. If exhaustive body-mention coverage matters, they need to invoke the script with a wider keyword list (e.g. include nicknames, ticker symbols, parent-company variants) or accept the tradeoff. **Generic English nouns (`bank`, `group`, `private`, `holdings`, `foundation`) are bad keyword choices on their own** — they degrade the slug-filter into a sector-wide net and silently 5–10× the fetch cost. Always pair them with the parent brand (`"DBS Bank"`, not bare `"Bank"`).
7. **Mixing publication voice in single-pub mode.** In single-pub mode, every "we" must refer to the publication named in the acronym. If you catch yourself writing "we at Travel Daily Media" in a Charlton report, rewrite the section.

Multi-publication-specific anti-patterns:

8. **First-person plural in combined mode.** Combined reports use neutral third person — there is no "we", "our", or "us". Before delivering a combined report, scan the prose for those words; any hit is a bug. The collective subject is the publication list (`Singapore Business Review, Retail Asia, and Asian Banking & Finance`), not "we".
9. **Conflating per-pub articles in the inventory.** Each article belongs to exactly one publication — the one whose `<slug>-filtered.json` it came from. Group it under that pub's section, even if the same brand was covered the same day on another pub. Don't deduplicate across pubs; each title is a distinct piece of earned coverage on its own publication.
10. **Aborting the whole run because one publication failed.** If one pub's scrape fails, log it and proceed with the rest. The combined report renders the survivors; surface the failures at Step 7. Don't kill a multi-pub job for a single network error.
11. **Resurrecting Recommendations.** The Recommendations section is removed from every report (single-pub and combined). Don't reach for `thought-leader-package-prices.md` and don't append a Recommendations section "for completeness." The reports stop at the Article Inventory.

## HTML template

Use this as the starting skeleton. Replace `{{...}}` placeholders. The 11pt body / 14pt headings rule is baked into the inline CSS — keep it intact so the HTML preview matches the DOCX you render in Step 6.

**This is the single-pub template.** For combined mode, see the modifications listed under "Combined-mode template modifications" below the skeleton.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{{brand}} — Earned Media Report</title>
<style>
  body { font-family: Helvetica, Arial, sans-serif; color: #222; margin: 40px; line-height: 1.45; font-size: 11pt; }
  h1 { font-size: 14pt; margin: 0 0 4px; }
  h2 { font-size: 14pt; margin-top: 28px; padding-bottom: 4px; border-bottom: 1px solid #ccc; }
  .meta { color: #555; margin-bottom: 18px; font-size: 11pt; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0 18px; font-size: 11pt; }
  th, td { border: 1px solid #bbb; padding: 8px 10px; text-align: left; vertical-align: top; font-size: 11pt; }
  th { background: #f2f2f2; }
  td.num, th.num { text-align: right; }
  .total td { font-weight: bold; background: #f7f7f7; }
  ul { margin: 6px 0 14px 22px; }
  ul li { margin-bottom: 6px; font-size: 11pt; }
  a { color: #1a4ea0; text-decoration: none; }
  a:hover { text-decoration: underline; }
  p { font-size: 11pt; }
</style>
</head>
<body>
<h1>{{brand}} — Earned Media Report</h1>
<div class="meta">
  <div><b>Prepared by:</b> {{publication}}</div>
  <div><b>Period:</b> {{period}}</div>
  <div><b>Date:</b> {{report_date}}</div>
</div>

<h2>Executive Summary</h2>
<p>{{exec_summary_para_1}}</p>
<p>{{exec_summary_para_2}}</p>

<h2>Financial Summary</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Total unique editorial pieces</td><td><b>{{total_pieces}}</b></td></tr>
  <tr><td>Flat media value per piece</td><td><b>USD 1,800</b></td></tr>
  <tr><td><b>Total Earned Media Value</b></td><td><b>USD ${{emv}}</b></td></tr>
  <tr><td>Coverage window</td><td>{{coverage_window}}</td></tr>
</table>

<h2>By year</h2>
<table>
  <tr><th>Year</th><th class="num">Pieces</th><th class="num">EMV (USD)</th></tr>
  {{by_year_rows}}
  <tr class="total"><td>Total</td><td class="num">{{total_pieces}}</td><td class="num">${{emv}}</td></tr>
</table>

<h2>By category</h2>
<table>
  <tr><th>Category</th><th class="num">Pieces</th><th class="num">Share</th></tr>
  {{by_category_rows}}
</table>

<h2>Strategic Observations</h2>
<ul>{{observation_bullets}}</ul>

<h2>Article Inventory</h2>
<p>All {{total_pieces}} unique editorial pieces published on {{publication}} in which {{brand}} or one of its sub-brands is the direct subject. Listed most recent first. Each carries the agreed flat valuation of USD 1,800.</p>
<table>
  <tr><th>#</th><th>Date</th><th>Article</th><th>Category</th></tr>
  {{inventory_rows}}
</table>

</body>
</html>
```

Inventory row format: `<tr><td>{{n}}</td><td>{{date}}</td><td><a href="{{url}}">{{title}}</a></td><td>{{category}}</td></tr>`

By-year row: `<tr><td>{{year}}</td><td class="num">{{pieces}}</td><td class="num">${{emv}}</td></tr>`

By-category row: `<tr><td>{{category}}</td><td class="num">{{pieces}}</td><td class="num">{{share}}%</td></tr>`

### Combined-mode template modifications

Apply these changes to the skeleton above when running in combined mode (2+ publications):

1. **Title block.** Set `{{publication}}` to the Oxford-comma list of selected pubs, e.g. `Singapore Business Review, Retail Asia, and Asian Banking & Finance`.

2. **Add `h3` styling** to the inline CSS so per-pub inventory subheaders render at 12pt bold:
   ```css
   h3 { font-size: 12pt; margin-top: 18px; margin-bottom: 6px; }
   ```

3. **Insert the "By publication" section** between Financial Summary and By year:
   ```html
   <h2>By publication</h2>
   <table>
     <tr><th>Publication</th><th class="num">Pieces</th><th class="num">EMV (USD)</th></tr>
     {{by_publication_rows}}
     <tr class="total"><td>Total</td><td class="num">{{total_pieces}}</td><td class="num">${{emv}}</td></tr>
   </table>
   ```
   By-publication row format: `<tr><td>{{publication_name}}</td><td class="num">{{pieces}}</td><td class="num">${{emv}}</td></tr>`

4. **Replace the single Article Inventory table** with a grouped layout — one subsection per pub, ordered by piece count descending:
   ```html
   <h2>Article Inventory</h2>
   <p>All {{total_pieces}} unique editorial pieces published across {{publication}} in which {{brand}} or one of its sub-brands is the direct subject. Grouped by publication, listed most recent first within each. Each piece carries the agreed flat valuation of USD 1,800.</p>

   <!-- Repeat this block once per publication, in piece-count-descending order -->
   <h3>{{pub_name}} — {{pub_pieces}} pieces</h3>
   <table>
     <tr><th>#</th><th>Date</th><th>Article</th><th>Category</th></tr>
     {{pub_inventory_rows}}
   </table>
   ```
   Per-pub `#` column resets to 1 inside each table — do not maintain a global counter.

5. **Strategic Observations and Executive Summary** stay structurally identical, but the prose inside is **neutral third person** — no first-person plural anywhere.

6. **Do not include a Recommendations block** — there is none in either mode.
