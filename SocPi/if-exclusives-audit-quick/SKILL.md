---
name: if-exclusives-audit-quick
description: Quick audit of IF/EXCLUSIVE article distribution using the URLs ALREADY in column A of the "IF & Exclusives" tab. Skips RSS feed scraping (Step 1a). Use when the user invokes /if-exclusives-audit-quick, asks for a quick or fast re-audit, says "audit what's in the sheet", says "don't wipe column A", asks to re-run the audit without re-collecting URLs from XML feeds, or when RSS feeds are timing out / unreliable and the team has already populated column A manually.
---

# IF & EXCLUSIVE Distribution Audit — Quick (skip URL collection)

Identical to `/if-exclusives-audit` **except Step 1a is skipped**. Column A is read as-is — never wiped, never repopulated from RSS feeds. Use when:

- The team has manually curated column A and doesn't want it overwritten.
- RSS feeds are flaky / timing out, and column A from a prior good run is fine.
- You just want a faster re-audit on the same URL set (saves the ~30-60s feed-fetch step).

## Dependency on the main skill

This skill **shares all scripts, secrets, and cache** with the main `if-exclusives-audit` skill. It does NOT have its own `scripts/`, `cache/`, or `secrets/` directories. All commands below run from the main skill's folder.

If `~/.claude/skills/if-exclusives-audit/` is missing on this machine, this skill cannot run. Install both folders together when porting.

## Publication selector — not supported in quick mode

The main skill accepts a per-publication filter (`/if-exclusives-audit SBR HKB`). Quick mode **does not** — by definition it uses whatever URLs are already in column A and skips the URL-collection step where the filter would normally apply.

If a user invokes the quick skill with acronyms (e.g. `/if-exclusives-audit-quick SBR HKB`), tell them their options:

1. **Run the full skill instead**: `/if-exclusives-audit SBR HKB` — wipes column A and writes only those pubs' URLs, then audits.
2. **Edit column A manually first**: delete URLs for pubs they don't want, then run `/if-exclusives-audit-quick` with no acronyms.

Do not silently ignore acronyms passed to the quick variant — that would mislead the user into thinking they audited only SBR/HKB when they actually audited everything in column A.

## Execution flow (orchestrator follows this exactly)

### Step 0 — Generate run-id, cd into main skill folder

```
RUN_ID=$(date +%s)
cd ~/.claude/skills/if-exclusives-audit/
mkdir -p cache/responses/$RUN_ID
```

All remaining steps run from inside `~/.claude/skills/if-exclusives-audit/`.

### Step 1 — Read column A into articles.json

**Skipping `collect_urls.py`.** Column A is whatever the team last saved there.

```
python scripts/fetch_articles.py \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives" \
    --out cache/articles.json
```

If `articles.json` shows 0 articles, column A is empty — fail loudly and tell the user to either run `/if-exclusives-audit` (full pipeline that auto-populates column A) or paste URLs into column A manually.

### Step 2 — Resolve account map (cached)

If `cache/account_map.json` exists, skip. Otherwise call SocialPilot `GroupList` → `AccountList` per group → build the map.

### Step 3 — Pull DeliveredPosts AND QueuedPosts (per article, parallel)

Same as main skill Step 3. Fire **all** `DeliveredPosts(q=<slug>)` and `QueuedPosts(q=<slug>)` calls in **a single parallel batch** (one Claude message with N tool-use blocks, where N = 2 × number of articles). No `account` filter needed.

### Step 3b — Save responses with `--auto-batch`

Write a single batch input file then run the saver once:

```
python scripts/save_mcp_response.py --auto-batch \
    --run-dir cache/responses/$RUN_ID \
    --input cache/responses/$RUN_ID/_batch_input.json
```

### Step 4 — Aggregate

```
python scripts/aggregate_posts.py --run-dir cache/responses/$RUN_ID \
    --account-map cache/account_map.json --out cache/posts.json
```

### Step 5 — Match

```
python scripts/match.py cache/articles.json cache/posts.json \
    --shortlinks cache/shortlinks.json --out cache/matches.json
```

### Step 6 — Report

```
python scripts/report.py cache/matches.json \
    --out-md runs/audit-$(date +%F).md --out-csv runs/audit-$(date +%F).csv
```

### Step 7 — Write to Google Sheet (auto-commit, NO feed report)

Pass `--skip-feed-report` so the sheet doesn't get a stale "XML Feed Issues" section. Quick mode never refreshes RSS feed status, so rendering the previous run's feed status would mislead the team into thinking it's current.

```
python scripts/write_to_sheet.py cache/matches.json \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives" \
    --skip-feed-report
```

`write_to_sheet.py` does NOT wipe column A. It only clears the area **below the article rows** to remove any stale feed-report data from a prior full audit, then writes a single one-line note saying RSS collection was skipped. The article URLs in A2:A_n are preserved.

### Step 8 — Output to user

Print the markdown table from `runs/audit-<date>.md` and confirm the sheet was updated.

## Strict rules

- **NEVER run `scripts/collect_urls.py`** — that's the entire point of this skill. Running it would wipe column A.
- All other strict rules from the main skill still apply (per-run-dir mandatory, never invent matches, never skip rows, posted permalink wins over scheduled marker, etc.).

## When to use this vs. the full skill

| Scenario | Use |
|---|---|
| Weekly audit cycle, fresh URLs from RSS | `/if-exclusives-audit` |
| Re-running on same URLs (e.g., recheck after team posted) | `/if-exclusives-audit-quick` |
| RSS feeds timing out / DNS errors | `/if-exclusives-audit-quick` (after manually populating column A) |
| Auditing a hand-curated list pasted into column A | `/if-exclusives-audit-quick` |
| First run on a new date window | `/if-exclusives-audit` |
