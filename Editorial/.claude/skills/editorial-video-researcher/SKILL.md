---
name: editorial-video-researcher
description: Generate AI-drafted discussion topics and C-suite interview questions for Charlton Media publications and append them directly to the "[2026] Discussion Topic" tab of the *Copy of 2025-2026 Asian Business Media* Google Sheet. Pulls each publication's top-read XML feed fresh on every run, dedupes by URL against column D, and processes a default of 3 articles per chosen publication (overrideable per-pub via `=N` syntax). Use when the user invokes `/editorial-video-researcher`, says "draft topics for SBR", "fill the discussion topic sheet", "do 3 articles for HKB", or asks for AI summaries + interview questions for any of the 11 publications (SBR, HKB, ABF, IA, RA, HCA, AP, GovMedia, MA, AT, REA).
---

# Editorial Video Researcher

End-to-end pipeline that turns top-read XML feed items from 11 Charlton Media publications into a row in the `[2026] Discussion Topic` tab: `Magazine | "AI" | one-paragraph summary | article URL | … | 5 C-suite questions`.

## Source of truth

- **Spreadsheet**: file ID `1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU` (*Copy of 2025-2026 Asian Business Media*).
- **Tab**: `[2026] Discussion Topic` only.
- **Dedupe column**: D (article URL). Any URL already present in column D is skipped.
- **Insert column**: A. Skill writes to the next empty row in column A on the tab.

## Publications (config.yaml)

| Abbrev | Full name |
|---|---|
| SBR | Singapore Business Review |
| HKB | Hong Kong Business |
| ABF | Asian Banking & Finance |
| IA | Insurance Asia |
| RA | Retail Asia |
| HCA | Healthcare Asia |
| AP | Asian Power |
| GovMedia | GovMedia |
| MA | Manufacturing Asia |
| AT | Asian Telecom |
| REA | Real Estate Asia |

## Execution flow

### Step 0 — Parse args

If the user invoked `/editorial-video-researcher` with arguments like `SBR=5 HKB ABF=2`, parse them into a `{abbrev: count}` dict. A bare abbrev without `=N` defaults to 3.

If no args were supplied, use **AskUserQuestion** with `multiSelect: true` to let the user pick one or more publications from the 11. Default count = 3 each. (If you want to support per-pub counts in the interactive flow, ask a second question after they pick.)

### Step 1 — Fetch every selected feed (always re-fetch)

For each chosen abbrev, run:

```
python scripts/fetch_feed.py --pub <abbrev> --out cache/feeds/<abbrev>.json
```

These are top-read feeds and they update — never reuse a cached XML.

`fetch_feed.py` automatically drops items whose URL contains any of the
`excluded_path_segments` listed in `config.yaml` (currently `/event-news/`,
`/commentary/`, `/co-written-partner/`, `/videos/`). Filtered items are
recorded in the output JSON's `excluded` array for traceability — the
`items` array contains only what's eligible to process. Step 3 picks from
`items` directly, so excluded URLs never reach dedupe or extraction.

### Step 2 — Read existing URLs from the sheet (once per session)

```
python scripts/sheet_existing_urls.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU \
    --tab "[2026] Discussion Topic" \
    --out cache/existing_urls.json
```

Load the resulting `urls` array into a Python set in your head. URL match is case-sensitive after stripping trailing `/`.

### Step 3 — Pick top-N new URLs per publication

For each pub:
1. Read `cache/feeds/<abbrev>.json` → list of `items`.
2. Filter out items whose `url` (after the same trailing-`/` strip) is in the existing URL set.
3. Take the first N from the filtered list, in feed order (top-read = most-popular first, which is what we want).
4. **If fewer than N new URLs are available**, use AskUserQuestion to confirm before continuing. Format the prompt like: *"Found 1 new article for HKB (wanted 3). Process the 1 available, skip HKB entirely, or stop the run?"*

### Step 4 — For each chosen URL: extract, generate, write

For each `(pub, url)`:

#### 4a. Extract the article

```
python scripts/fetch_article.py --url <url> --out cache/articles/<slug>.json
```

`<slug>` = the last path segment of the URL. The script writes `{title, deck, body, paragraphs, url}` extracted from the page's `<script type="application/ld+json">` `NewsArticle` block. If the script exits 4 ("NO JSON-LD NewsArticle"), skip this URL with a logged warning and move on.

#### 4b. Generate the TOPIC (column C) — Prompt #1

Feed the model the article's `title`, `deck`, and `body`, with this exact prompt:

> As an experienced business researcher/writer for a leading business news outlet, your challenge today is to extract crucial insights from a research/report/study. Your goal is to summarize the article into a one short paragraph, ensuring to include no misleading information, highly relevant and updated facts and figures directly mentioned in the material, and to cite the source in the summarisation. This will serve as a foundational guide to develop a relevant, issue-based video discussion topic focusing on financial markets, corporate affairs, and economic policies. Please ensure your summary captures the essence of the material, highlighting innovative insights, challenges, and future directions mentioned in the material. Your concise summarisation of the material will enable us to craft an insightful interview topic that resonates with our viewership's interests in market trends, regulatory landscapes, and industry innovations.

Cite the publication's full name in the summary (e.g. *"(Source: Singapore Business Review)."*). The output is a single paragraph — that becomes column **C**.

#### 4c. Generate 3 topics × 7–8 questions — Prompt #2

Feed the summary from 4b into this exact prompt:

> As an experienced business journalist for a leading business news outlet, your audience consists of C-level executives from premier companies within the industry. Your task is to delve into the provided material to unearth three topics that hold the potential to ignite engaging discussions with a C-level executive during a dinner conversation. Once these topics are identified, you are to develop 5 to 10 insightful questions for each, aimed at C-level executives, while adhering to the guidelines outlined to resonate with your sophisticated readership and uphold the editorial excellence of your publication.
>
> Guidelines for Crafting Questions:
>
> Executive Appeal: Tailor your questions to capture the interests of C-level executives deeply involved in pivotal strategic decisions, focusing on subjects that could significantly influence their company's or industry's future trajectory.
>
> Trend-centric: Concentrate your questions on dissecting industry shifts, emerging trends, or unveiling novel insights that could reshape the business landscape, aiming to reveal underreported or new phenomena.
>
> Topic Cohesion: Ensure each set of questions is unified around a single, well-defined theme to maintain focused and meaningful discourse, thereby enriching the depth and value offered to your audience.
>
> Conversational Format: While maintaining professionalism, craft your questions to suit a conversational tone, suitable for a live broadcast interview, facilitating a natural and engaging dialogue flow.
>
> Insightful Engagement: Design questions to draw out unique insights or perspectives, potentially unknown to the public or even among executive circles, with the aim of fostering enlightening discussions that enrich your audience's understanding.
>
> Tone: Keep a conversational yet formal tone throughout, reflecting the manner in which C-level executives discuss such topics among peers — professional but with an ease that encourages open, insightful exchanges.
>
> Format: The first question must begin with "What" and orient the conversation around the current state of the industry. It should surface what is happening, what is changing, or what forces are driving those changes. This grounds the interview in real-world context before moving into deeper or more specific topics.
>
> Execution Steps:
>
> Initial Analysis: Begin by concisely summarizing the core findings and their significance from the study, emphasizing their importance to your C-level executive readership.
>
> Topic Identification: Identify the three most engaging topics within the study, signifying considerable business trends or insights. Provide a succinct justification for each selected topic, highlighting its relevance in the current business climate.
>
> Question Formulation: For each chosen topic, devise 5 to 10 questions following the guidelines provided. These questions should not only prompt reflection but also prompt executives to divulge insights or viewpoints rarely shared in their public statements or interviews.

#### 4d. Narrow to 5 final questions — Prompt #3

Feed the 3-topics-with-questions output from 4c into this exact prompt, with the publication's full name substituted into `[specified]`:

> As an experienced business journalist for a leading business news outlet, your audience consists of C-level executives from premier companies within the [PUBLICATION_FULL_NAME] industry. Your task is to choose questions that hold the potential to ignite engaging discussions with a C-level executive during a dinner conversation. Do this by choosing 5 QUESTIONS from each suggested topics, making sure that each are short yet insightful questions aimed at C-level executives in the industry.
>
> That specified industry is based on from which xml did you get that article

**Important**: prompt #3 as written returns 5 questions per topic (15 total). The user has confirmed they only want **5 questions total**, picked across all topics. After running prompt #3, perform one more selection step in your head: pick the 5 strongest questions from the 15, prioritising the lead "What" question that orients the conversation around current state. Those 5 are what goes into column G, joined by `\n\n` (blank line between each).

#### 4e. Find next empty row

```
python scripts/sheet_next_empty_row.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU \
    --tab "[2026] Discussion Topic"
```

Stdout is the row number to write.

#### 4f. Write the row

```
python scripts/sheet_write_row.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU \
    --tab "[2026] Discussion Topic" \
    --row <N> \
    --magazine "<full publication name>" \
    --by AI \
    --summary "<paragraph from 4b>" \
    --url "<article URL>" \
    --questions "<q1>\n\n<q2>\n\n<q3>\n\n<q4>\n\n<q5>"
```

The script's `--summary` and `--questions` flags accept literal `\n` sequences and unescape them to real newlines before writing. Pass the full publication name (e.g. `Singapore Business Review`, not `SBR`) to match the convention of the existing AI-generated rows.

### Step 5 — Final report

After all writes, print a per-pub summary to the user:
- Pub abbrev
- N processed (with row numbers)
- N skipped (already in sheet)
- Any failures (URLs that errored on fetch/extract)

## Strict rules

- **Never reuse a cached feed XML.** Always re-fetch in step 1.
- **Never bypass the path-segment exclusion filter.** Articles under `/event-news/`, `/commentary/`, `/co-written-partner/`, or `/videos/` are not in scope for the discussion-topic pipeline — they're event recaps, opinion, sponsored content, and video posts respectively.
- **Never write a row whose URL is already in column D.** Dedupe is mandatory.
- **Never skip the AskUserQuestion confirmation** when a feed has fewer new articles than requested for that pub.
- **Never use the publication abbreviation in column A.** Always the full name from `config.yaml`.
- **Never write to columns E, F, H, or I.** Only A, B, C, D, G.
- **Column B is always the literal string `AI`** (not the model name, not "Claude").
- If `fetch_article.py` returns no JSON-LD NewsArticle, skip that URL — do not fabricate a summary from the title alone.

## Files

```
editorial-video-researcher/
├── SKILL.md                  this file
├── config.yaml               sheet ID, tab, 11 pubs (abbrev → name + feed), browser headers
├── scripts/
│   ├── fetch_feed.py         XML download + parse → JSON list of items
│   ├── fetch_article.py      HTML fetch + JSON-LD NewsArticle extract
│   ├── sheet_existing_urls.py  gspread col_values(4) → URL set
│   ├── sheet_next_empty_row.py gspread col_values(1) → first gap row number
│   └── sheet_write_row.py    gspread batch_update of A/B/C/D/G
├── secrets/
│   ├── .gitignore            ignores *.json
│   └── gsheets-sa.json       Google service-account key (gitignored)
└── cache/
    ├── feeds/<abbrev>.json   last fetched feed per pub (overwritten each run)
    ├── articles/<slug>.json  extracted Title/Deck/Body (kept across runs)
    └── existing_urls.json    last sheet column-D snapshot (refreshed each run)
```

## Re-running

The skill is idempotent: dedupe ensures the same URL is never written twice. Safe to invoke any time. Each run re-fetches XML and re-reads column D so the snapshot is always current.
