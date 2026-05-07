---
name: if-exclusives-audit
description: Audit IF and EXCLUSIVE article distribution across 20 Charlton Media publications and their Facebook, Instagram, LinkedIn, and X accounts via SocialPilot. Detects both posted and scheduled posts. Use when the user asks for a distribution audit, asks "which articles weren't posted", asks "which are scheduled", asks for a coverage/SocialPilot/IF/EXCLUSIVE report, or invokes /if-exclusives-audit. Reads the canonical "Commercial SocPi - Links" Google Sheet (tab "IF & Exclusives") as the source of truth, pulls delivered + queued posts from SocialPilot, writes per-platform permalinks (or SCHEDULED markers) directly to columns D-H of the sheet.
---

# IF & EXCLUSIVE Distribution Audit (v2)

End-to-end audit of IF and EXCLUSIVE article distribution. Source of truth is the Google Sheet; SocialPilot is the truth for what was actually posted **and** what is queued to post. Matching is deterministic Python — never LLM-judged.

## Source of truth (strict)

- **Spreadsheet**: file ID `1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk` ("Commercial SocPi - Links").
- **Tab**: `IF & Exclusives` only.
- **Column A** = article URL. Every row is treated as IF or EXCLUSIVE (URL path is unreliable; do not filter).

## Output (what lands in the sheet, columns D-H)

| Col | Header | Cell content |
| --- | --- | --- |
| D | Facebook URL | `=HYPERLINK("<permalink>","<post headline>")`, or `SCHEDULED 2026-05-02 10:00`, or empty |
| E | Instagram URL | same |
| F | LinkedIn URL | same |
| G | X URL | same |
| H | Status | one of: `COMPLETE` `PARTIAL` `SCHEDULED` `MISSING` `DUPLICATE ISSUE` |

Posted cells use a `=HYPERLINK()` formula so the team sees the actual post headline as clickable text. Headline = `postTitle` from SocialPilot, or first line of `postDesc` if `postTitle` is empty, capped at 120 chars. Falls back to a bare URL if no headline is available.

Status hierarchy: `DUPLICATE ISSUE` > `COMPLETE` > `PARTIAL` > `SCHEDULED` > `MISSING`. `SCHEDULED` only fires when nothing is actually posted but at least one queued post exists.

## SocialPilot platform IDs (confirmed)

| Platform | platformId |
| --- | --- |
| Facebook | 1 |
| Twitter / X | 2 |
| LinkedIn | 3 |
| Instagram | 9 |

## Execution flow (the orchestrator follows this exactly)

### Step 0 — Generate run-id

In `Bash`: `RUN_ID=$(date +%s) ; mkdir -p ~/.claude/skills/if-exclusives-audit/cache/responses/$RUN_ID`. Use this dir for every response in this run.

### Step 1a — Collect URLs from XML feeds (auto-populate column A)

Scrape RSS feeds from the **"IF & Exclusives XML"** tab (column A = "In Focus" feeds, column B = "Exclusives" feeds, ~19 publications), filter `<item>`s by the date range in **B1:C1 of "IF & Exclusives"** (format `MM-DD-YYYY`, inclusive on both ends), dedupe (an article in both IF and Exclusive feeds for the same pub appears once), and write the resulting URLs into column A of "IF & Exclusives". **This WIPES rows 2+ of column A** and replaces them. Header (row 1) is preserved.

```
python scripts/collect_urls.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives" \
    --xml-tab "IF & Exclusives XML" \
    --log cache/url_collection_log.txt
```

Inspect `cache/url_collection_log.txt` for warnings:
- `FETCH` — feed URL unreachable / timeout / 4xx-5xx (real problem, surface to user)
- `PARSE` — feed body wasn't well-formed XML (real problem, surface to user)
- `EMPTY` — feed parsed fine but had 0 items in the date window (informational, often normal)
- `PUBDATE` — individual `<item>` had unparseable `pubDate` (item skipped, rest of feed kept)

The script exits 4 if **zero URLs result** from the date window — this prevents silently wiping the audit list when the date range is misconfigured. If you genuinely want to proceed with an empty audit, re-run with `--allow-empty`.

### Step 1b — Read column A into articles.json (gspread direct)

After Step 1a populates column A, read it into the canonical articles.json:

```
python scripts/fetch_articles.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives" \
    --out cache/articles.json
```

Fallback (only if SA file is unavailable): use Drive MCP `download_file_content` to export CSV, then `python scripts/fetch_articles.py cache/sheet.csv --out cache/articles.json`.

### Step 2 — Resolve account map (cached)

If `cache/account_map.json` exists, skip. Otherwise call `GroupList` (paged) → `AccountList` per group → build the map. Persist.

### Step 3 — Pull posts per article (one parallel batch)

**Fire ALL MCP calls in a SINGLE message with parallel tool-use blocks.** No `account` filter needed. The saver auto-routes by `loginId` and `platformId` from each record.

For each article in `articles.json`, queue:

```
mcp__ae062…__DeliveredPosts(q=<article-slug>,
                            startDate=<window-start>, endDate=<window-end>, limit=20)
mcp__ae062…__QueuedPosts   (q=<article-slug>,
                            startDate=<window-start>, endDate=<window-end>, limit=20)
```

That's **2 calls per article** — for 21 articles, **~42 calls total**, vs the old 78. Each call returns up to 4 posts (one per platform) so `limit=20` is plenty.

Use the article's slug (the last path segment of the URL). Examples:
- `royal-garden-kowloon-east-targets-families-and-pet-owners`
- `seoul-and-tokyo-residential-markets-stay-resilient`

Date window: from earliest article date − 30 days to today + 30 days. SocialPilot's `q=` searches post descriptions where pubs' captions contain the full article URL with the slug.

**Save ALL responses in EXACTLY TWO steps:**

### Step 3a — Write the batch input file (ONE `Write` call)

Build a single JSON array containing every (slug, kind, response) entry, and write it to `cache/responses/$RUN_ID/_batch_input.json` using ONE `Write` tool call:

```json
[
  {"slug": "<slug-1>", "kind": "delivered", "response": <raw MCP response, unmodified>},
  {"slug": "<slug-1>", "kind": "queued",    "response": <raw MCP response, unmodified>},
  {"slug": "<slug-2>", "kind": "delivered", "response": <raw MCP response, unmodified>},
  ...
]
```

### Step 3b — Run the saver (ONE `Bash` call)

```
python scripts/save_mcp_response.py --auto-batch \
    --run-dir cache/responses/$RUN_ID \
    --input cache/responses/$RUN_ID/_batch_input.json
```

The saver writes one `<slug>__<kind>.json` file per entry. The aggregator derives `pub` and `platform` from each record's `loginId`/`platformId` against `account_map.json`.

### HARD RULES — DO NOT IMPROVISE THIS STEP

- **DO NOT** call the `Write` tool 38 separate times to create individual response files. That is what the batch is for.
- **DO NOT** "minimize" or "filter" responses to save context. Pass them through verbatim. Profile-pic URLs and other bulky fields are harmless — the aggregator ignores them.
- **DO NOT** invoke `save_mcp_response.py` 38 times in a loop. Use `--auto-batch` ONCE.
- **DO NOT** write your own Python loader script. The saver already does this.
- **DO NOT** use `--auto-flat` for the main flow — it's a fallback only for single oversized responses that can't fit in the batch input file.

The cost of doing this step "cleverly" with per-file Writes is ~10 minutes of round-trips. The cost of one Write + one Bash is ~5 seconds. Trust the batch.

### IF YOU MUST FILTER — exact keep-list (and why)

If context size genuinely forces filtering, every record MUST retain these fields. Stripping any of them causes the aggregator to drop records silently (well, loudly now — it will exit 3). Past sessions have stripped `postId` and lost everything; do not repeat that mistake.

Per-record keep-list:

| Field | Required for | Notes |
|---|---|---|
| `postId` | Aggregator dedup | **Drop = total failure.** |
| `loginId` | Pub/platform routing | **Drop = total failure.** |
| `accountId` *or* `platformId` | Platform fallback when loginId not in account_map | One of the two is enough. |
| `postUrl` | Matcher fast-path | Empty for IG — that's normal, slug fallback handles it. |
| `postDesc` | Matcher slug-fallback + duplicate detection | **Do NOT trim.** IG matching depends on the article URL or slug appearing in this string. |
| `redirectUrl` | Permalink written to sheet | This is what shows up in column D-G. Drop it and the sheet gets blanks. |
| `postDate` *or* `postTimeFormat` | Timestamps | At least one. |
| `scheduleDateUtc` | Scheduled posts only | Skip for delivered. |

**Discardable** (safe to drop if you must): `postImage`, `thumbImage`, `profilePicture`, `accountUrl`, `accountUsername`, `accountExtraParam`, `extraData`, `commentData`, `tagIds`, `companyId`, `uniqueId`, `formatedPostDate`, `postDateFormat`, `createdOn`, `via`, `color`, `accessType`, `isReconnect`, anything starting with `is*`.

If `aggregate_posts.py` exits with code 3 saying records were dropped, the saved responses were over-filtered. Restore the full responses or re-fetch.

> **Fallback flow:** if the per-article approach somehow misses posts, the legacy per-pub-platform pull (DeliveredPosts/QueuedPosts with `account=<loginId>` and `q=<pub-domain>`) still works. The aggregator accepts both filename shapes.

### Step 4 — Aggregate

```
python scripts/aggregate_posts.py --run-dir cache/responses/$RUN_ID \
    --account-map cache/account_map.json --out cache/posts.json
```

Each post is tagged `kind: posted` or `kind: scheduled`.

### Step 5 — Match

```
python scripts/match.py cache/articles.json cache/posts.json \
    --shortlinks cache/shortlinks.json --out cache/matches.json
```

URL-first; fuzzy fallback flagged. Posted matches go in `posted_matches`, scheduled in `scheduled_matches`.

### Step 6 — Report

```
python scripts/report.py cache/matches.json \
    --out-md runs/audit-$(date +%F).md --out-csv runs/audit-$(date +%F).csv
```

### Step 7 — Write to Google Sheet (auto-commit)

Only proceeds if `secrets/gsheets-sa.json` exists. **Default is auto-commit** — the orchestrator writes to the sheet immediately, no preview gate. The whole point of the skill is to land the audit in the sheet on every run.

```
python scripts/write_to_sheet.py cache/matches.json \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives"
```

Only columns D-H are touched (writes are atomic via `worksheet.batch_update`). Use `--dry-run` only when the user explicitly asks for a preview.

### Step 8 — Output to user

Print the markdown table from `runs/audit-<date>.md` and confirm the sheet was updated.

## Strict rules

- **Per-run-dir is mandatory.** Never glob the global tool-results dir.
- **Never invent matches.** If uncertain → leave cell empty.
- **Never skip rows.** All rows from column A appear in the table and the sheet output.
- **Never modify columns A-C of the sheet.** Only D-H.
- **Posted permalink wins over scheduled marker** for cell display when both exist.

## File layout

```
~/.claude/skills/if-exclusives-audit/
  SKILL.md                this file
  config.yaml             groups map, platform IDs, thresholds
  scripts/
    fetch_articles.py     CSV → articles.json
    save_mcp_response.py  stdin JSON → file
    aggregate_posts.py    per-run-dir → posts.json (tags posted/scheduled)
    match.py              articles + posts → matches.json
    report.py             matches → markdown + CSV + metrics
    write_to_sheet.py     matches → cells D-H of the sheet (dry-run default)
  cache/
    sheet.csv
    articles.json
    account_map.json
    posts.json (current run)
    matches.json (current run)
    shortlinks.json
    responses/<run-id>/   per-run JSON dump from each MCP call
  runs/audit-YYYY-MM-DD.{md,csv}
  secrets/gsheets-sa.json (gitignored)
```

## Re-running

Each run is fully isolated — old `cache/responses/<run-id>/` dirs do not contaminate. Safe to invoke any time. Sheet writes are atomic via `worksheet.batch_update`.
