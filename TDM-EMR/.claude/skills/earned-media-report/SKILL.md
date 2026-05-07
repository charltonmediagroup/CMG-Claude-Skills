---
name: earned-media-report
description: Generate an Earned Media Report DOCX for a brand by scraping Travel Daily Media. Walks the user through proposing brand keywords, runs the scrape helper, reviews borderline articles for the user to approve, drafts the report content, and renders it to a Word document. Use when the user types `/earned-media-report <brand>`, asks to "produce an earned media report" for a hospitality / travel brand, or asks to replicate the Minor Hotels report format for another brand.
---

# Earned Media Report

You are helping the user produce a polished DOCX Earned Media Report on the brand they name. The reference structure is in [Minor Hotels — Earned Media Report.pdf](../../../Minor%20Hotels%20—%20Earned%20Media%20Report.pdf) — match its sections, tone, and table layout.

The mechanical scraping is done by `scripts/earned-media-report.mjs` (Node 18+, no dependencies). Your job is the judgment work around it: keyword proposal, borderline-case review, narrative writing, and DOCX rendering.

## Workflow

### 1. Verify Node 18+

Run `node --version`. If it's not installed or below v18, tell the user to install Node.js 18+ from nodejs.org and stop. Built-in `fetch` requires v18.

### 2. Propose the brand-keyword list

The keyword list is what separates "article about this brand" from "article that mentions this brand in passing." It must include:

- The parent brand name
- Every sub-brand the group operates under
- Major sister brands and any brand that is co-marketed under the same group

For Minor Hotels, the list was: `Minor Hotels, Anantara, Avani, Tivoli, NH, Oaks, nhow, Colbert Collection, Wolseley, Elewana`.

Draft the equivalent list for the user's brand using your own knowledge. If you're not confident about the brand's full sub-brand portfolio (especially for less-familiar regional groups), use WebSearch to confirm. Then **show the list to the user and get explicit approval or edits before running the scrape.** Do not run the helper with an unconfirmed list.

When you propose the list, briefly explain *why* each sub-brand is included so the user can spot omissions.

### 3. Run the scrape helper

Once the keyword list is approved:

```bash
node scripts/earned-media-report.mjs \
  --brand "<Brand Name>" \
  --keywords "<comma,separated,list>"
```

Outputs land in `output/earned-media/.cache/` (a hidden working subfolder so the visible `output/earned-media/` folder only contains DOCX deliverables):

- `.cache/<slug>-raw.json` — every article the search returned, with `kept`/`dropReason` flags. Use this for QA — it tells you *why* each article was dropped.
- `.cache/<slug>-filtered.json` — kept articles only, sorted newest-first. This is the dataset for the report.

The script's stdout summary tells you how many pages were scanned, how many unique URLs were found, and how many passed the filter. **Surface those numbers to the user** before moving on.

### 4. Manual QA — flag borderline articles

Read `.cache/<slug>-filtered.json`. Scan titles plus raw categories and identify articles that should *probably* be excluded even though they passed the keyword filter. The patterns to flag:

| Pattern | Why exclude |
|---|---|
| Multi-brand roundups ("Where to stay in...", "Top 10...", "Best hotels for...") | Brand isn't the subject |
| Coalition / industry-body / petition pieces (Open Thailand Safely, GHA Discovery, HBX MarketHub) | Brand is one of many participants |
| Partner-platform integration mentions (Sabre, Atiom, OTA partner stories) | Subject is the platform, brand is incidental |
| Q&A / feature where brand is mentioned but not the subject | Subject is the interviewee or topic |
| Anything where the title doesn't make the brand the actor | Passing-mention false positive |

Compile a candidate exclusion list with article URLs and a one-line reason for each. **Show it to the user and get explicit approval before regenerating numbers.** Do not silently drop anything.

If the count changes between drafts (e.g., 30 → 27 after exclusions), state both numbers explicitly when you report back. Don't paper over count drift.

### 4.5 Read the Media Kit

Open `Media Kit.pdf` at the TDM-EMR workspace root using the `Read` tool (or the `anthropic-skills:pdf-reader` skill). Internalize the product catalog: prices, deliverables, target audiences, and available events. You will reference specific products **by name and unit price** in the Recommendations section in Step 5 — no generic "consider expanding partnerships" phrasing.

Key product anchors you can rely on:

- **Native Content (creation + distribution)** — USD 4,200/article, includes 1-month featured rotation + 8 newsletter regions + 12-month social campaign.
- **Native Advertising / Advertorial (distribution only)** — USD 2,800/article.
- **Executive Interview** — Written USD 2,240, Audio podcast USD 2,856, Video Zoom USD 3,500.
- **Press Release distribution** — USD 599 (1–4) / USD 539 (5–9) / USD 479 (10–19), or SEO URL link USD 199.
- **Bespoke Roundtable** — Solo USD 12,000 / Joint USD 4,500 each (3 sponsors).
- **Email Marketing (EDM/SOLIS)** — Global USD 4,800 / Single region USD 2,400.
- **Banner advertising / Website Takeover** — USD 2,273–4,999/week depending on placement.
- **Competitions** — USD 2,310 (2-week run).
- **TDM Events to sponsor**: Global Summits (Bangkok / Dubai / Singapore 2026), TDM Travel Trade Excellence Awards (Dubai Sep 26, Bangkok Oct 26, KL Nov 26, Singapore Nov 26, Hong Kong Jan 27), IWTA Awards (Aug 26).

If the Media Kit changes (new products, new prices, new events), it overrides this list — always read the current PDF before drafting.

### 5. Generate the report content

Compose the full report content following the Minor Hotels structure. **Match the prose length of the reference PDF** ([Minor Hotels — Earned Media Report.pdf](../../../Minor%20Hotels%20—%20Earned%20Media%20Report.pdf)) — the goal is calm editorial commentary, not a sales deck. If a paragraph is creeping past the targets below, cut it back.

**Voice — non-negotiable.** Write in **first person plural**. Travel Daily Media is the speaker. Use *we*, *our*, *us*. Examples:

- ✅ *"We published 82 unique editorial pieces in which Minor Hotels or one of its brands is the direct subject."*
- ✅ *"Our coverage of the group has accelerated noticeably in recent years."*
- ❌ *"TDM published 82 pieces…"* / *"The publication's coverage has accelerated…"* / *"They covered the group across 82 articles…"*

Apply this rule in every narrative paragraph: Executive Summary, Strategic Observations, Recommendations, and the inventory preamble.

**Length anchors (counted directly from the reference PDF):**

| Section | Target | Shape |
|---|---|---|
| Executive Summary | ~160 words across 2 paragraphs (P1 ~60, P2 ~100) | P1 = scoped intro + EMV figure (3 sentences). P2 = narrative on what drove the count (4 sentences). |
| Strategic Observations | ~185 words across 4 bullets | Each bullet 2–3 sentences (~35–55 words). Open with a bold thesis sentence, then 1–2 supporting sentences. |
| Recommendations | ~150 words: 1 short framing sentence + 3–4 numbered items | Each item = bold title (product/event + USD price) + 1–2 sentence proposal. Total per item: ~30–45 words. |

**Sections in order:**

1. **Title block** — `<Brand> — Earned Media Report`, "Prepared by: Travel Daily Media", period (earliest article date – today's date), date.
2. **Executive Summary** — match the length anchor above. Cover total pieces, EMV, and the narrative of what drove the count (sub-brand mix, standout years, story types). Tailor to what the data shows; don't reuse Minor Hotels phrasing.
3. **Financial Summary** — table with `Total unique editorial pieces`, `Flat media value per piece` (USD 1,800), `Total Earned Media Value` (`pieces × $1,800`), `Coverage window`.
4. **By year** — pieces and EMV per calendar year, ordered ascending, with a Total row.
5. **By category** — pieces and share-% per taxonomy bucket, ordered descending by count.
6. **Strategic Observations** — 4 bullets matching the length anchor above. Cover: dominant theme, trend over time, dominant sub-brand(s), gaps in higher-value editorial formats. Be specific — name properties, deals, executives where the dataset supports it.
7. **Recommendations** — see the format rules below.
8. **Article Inventory** — full table, newest-first, columns: `#`, `Date`, `Article` (hyperlinked title using the **canonical URL from the dataset**), `Category`. EMV is implicit (every row = $1,800).

**Recommendations format — soft pitch, not a hardsell.** Numbered list of 3–4 items. Each item is a **bolded title containing the product name and unit price**, followed by **1–2 sentences only** describing the proposal. Open the section with one short framing sentence; everything else lives inside the numbered items.

Pattern to follow:

> Given the gaps the dataset surfaces, we would propose [N] targeted programmes that map to formats and audiences where [Brand] currently has the lightest coverage.
>
> **1. [Product or programme title] — USD [price] [per piece / per send / per article].** [One-sentence proposal naming the brands, regions, themes, or events involved, with one optional brief upgrade or context note.]

Target shape (calibrated against the Hilton sample — short, calm, no math, no data callouts):

> **1. Quarterly Written Executive Interview series — USD 2,240 per piece.** We would propose a quarterly programme rotating across regional CEOs (Asia Pacific, EMEA, Middle East) and luxury-brand heads (Waldorf Astoria, Conrad, Canopy), with the option of upgrading to a Video Executive Interview (USD 3,500) for major brand-platform moments.
>
> **2. Native Content programme — USD 4,200 per article.** A series of three pieces over twelve months anchored on themes already visible in the data — the 2030 Travel With Purpose framework, the lifestyle-expansion thesis (Spark / Tempo / Canopy / Graduate), or the Small Luxury Hotels of the World partnership.
>
> **3. TDM Travel Trade Excellence Awards Asia 2026 sponsorship — Singapore, 24 November 2026.** The Asia awards in Singapore are the natural fit given the group's Asia-Pacific concentration in our coverage; for Middle East and Americas readership, TDM Travel Trade Excellence Awards Middle East (Dubai, 29 September 2026) is the equivalent.
>
> **4. Asia Single-Region EDM — USD 2,400 per send.** A quarterly branded EDM into our Asia daily list (101K+ subscribers) lets the brand drive direct traffic alongside earned coverage at the moment of intent.

**Drop in every recommendation:**

- **Inline math.** No `4 × USD 2,240 = USD 8,960 annually` or any per-year/per-cycle multiplication. The unit price in the title is the only number.
- **Data callouts.** No *"With only one Interview-category piece across 4.7 years…"* or *"Partner Articles appear once in the entire dataset…"* inside the recommendation text. Those observations belong in Strategic Observations; Recommendations is forward-looking.
- **Benefit puff.** No *"Each interview converts a senior executive into a durable thought-leadership asset…"* or *"…earn the one-month Featured rotation, eight-region newsletter coverage, and twelve-month social campaign that come with the format."* The Media Kit explains what comes with each format; the recommendation just states the proposal.

**Keep in every recommendation:**

- Bold title with product/programme name and unit USD price (or, for sponsored events, the event name + date + location).
- The actual proposal: brands, regions, themes, properties, executives, events, dates as relevant.
- One optional upgrade or alternative aside if it adds genuinely useful context (e.g., naming a parallel awards event in another region).

Pick the 3–4 items grounded in what the dataset actually shows. Don't list every product TDM offers; the recommendations should answer *"what would move the needle for this brand given what we already cover and don't cover?"*

**Critical rules:**

- **Pull URLs from the dataset only.** Never reconstruct a URL from a title slug. If a URL is missing from the dataset, leave the title un-linked rather than guessing.
- **Sanity-check the totals before delivering.** Sum of `By year` pieces == sum of `By category` pieces == length of inventory. If they don't match, fix the data, not the table.
- **EMV is always `pieces × $1,800`.** Don't introduce per-article variation.
- **Typography.** Body text and table cells: 11pt. Headings (`h1` and `h2`): 14pt. The HTML template enforces this; the DOCX in Step 6 must match.

### 6. Render the DOCX

Read the filtered dataset from `output/earned-media/.cache/<slug>-filtered.json` (the helper writes JSON into the `.cache/` subfolder so the visible `output/earned-media/` folder only contains DOCX deliverables). Use the `anthropic-skills:docx` skill to produce `output/earned-media/<slug>.docx` from the content you composed in Step 5. Pass the report as Word-native structures: paragraphs, headings (Heading 1 / Heading 2 styles), tables, hyperlinks. Match the typography rules:

- Body paragraphs and table cells: **11pt**.
- Heading 1 and Heading 2: **14pt**.

**Output only the DOCX.** Do not write an HTML preview alongside it. The visible `output/earned-media/` folder should contain only `<slug>.docx` files (plus the hidden `.cache/` subfolder).

If the user wants to tweak something after seeing the DOCX (re-word an observation, drop another article, etc.), update the content and re-render — don't hand-edit the DOCX in place, since the next regeneration would overwrite the changes.

### 7. Final check

Before declaring done, confirm to the user:

- Total article count (and any change from earlier drafts)
- Total EMV
- Path to the DOCX
- That every URL in the inventory was pulled from the canonical link tag (not reconstructed)
- That each recommendation is 1–2 sentences, names a TDM product/event with its unit price (or date + location for sponsored events) in the bold title, and contains no inline math or data callouts

## Anti-patterns from past runs

These mistakes happened in the original Minor Hotels run. Don't repeat them:

1. **Fabricating URLs.** When asked for an article link, the previous run reconstructed one from the title slug rather than looking it up in the dataset. Always pull URLs from `.cache/<slug>-filtered.json`.
2. **Silently dropping articles between drafts.** When the filter or exclusion list tightens, the count changes — surface that explicitly. Don't let the user notice the drift on their own.
3. **Treating passing mentions as subject coverage.** The original first-pass had 187 articles (including roundups, loyalty stories, and coalition pieces) before the brand-keyword-in-title-or-first-350-chars filter brought it to 82. The script applies that filter automatically, but the manual QA pass exists because the filter alone misses roundups that *do* mention the brand within the first paragraph.
4. **Not flagging the 2-letter-token false-positive risk.** Keywords like `NH` (substring match) can match unrelated words. When you scan the dataset, look for any retained article where the keyword appears only as part of a different word and propose it for exclusion.
5. **Padding recommendations with marketing prose.** A previous draft had each recommendation running 4–5 sentences with inline math (`4 × USD 2,240 = USD 8,960`), data-callout setup (*"With only X pieces in Y years…"*), and benefit puff (*"Each interview converts a senior executive into a durable thought-leadership asset…"*). The format is **bold title + 1–2 sentences**. Anything else reads as a sales pitch.

## HTML template

Use this as the starting skeleton. Replace `{{...}}` placeholders. The 11pt body / 14pt headings rule is baked into the inline CSS — keep it intact so the HTML preview matches the DOCX you render in Step 6.

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
  <div><b>Prepared by:</b> Travel Daily Media</div>
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

<h2>Recommendations</h2>
<p>{{recommendations}}</p>

<h2>Article Inventory</h2>
<p>All {{total_pieces}} unique editorial pieces published on Travel Daily Media in which {{brand}} or one of its brands is the direct subject. Listed most recent first. Each carries the agreed flat valuation of USD 1,800.</p>
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
