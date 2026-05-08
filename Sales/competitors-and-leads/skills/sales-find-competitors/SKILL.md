---
name: sales-find-competitors
description: Find APAC competitors for every CMG client in the SBR tab whose 'Checked' column is not 'Yes'. Reads the 'Existing Clients (2021 to 2025)' Google Sheet, runs SerpAPI search per client, then has Claude pick 5–10 verifiable competitors and append rows to the Competitors tab. Mirrors Phase 1 of the n8n 'Sales - Competitors and Leads' workflow. Use when the user asks to find competitors, run /sales-find-competitors, or kick off the prospecting pipeline at the top.
---

# /sales-find-competitors

Phase 1 of the competitors-and-leads pipeline. Finds APAC competitors for every CMG client in the SBR tab that hasn't been processed yet (`Checked != Yes`).

## Where the code lives

`~/.claude/competitors-and-leads/` — single canonical bundle. The `run.py` CLI has phase subcommands. The reasoning step happens in your conversation with the user, between the `phase1-collect` and `phase1-write` calls.

## Runbook

### Step 1 — Show the candidate count first

```
python ~/.claude/competitors-and-leads/run.py phase1-collect --dry-run
```

Print the candidate count to the user. If it's > 5 clients, **ask** before continuing — Phase 1 makes one SerpAPI call per client and the user may want to scope down.

### Step 2 — Collect search results

```
python ~/.claude/competitors-and-leads/run.py phase1-collect
```

This writes `~/.claude/competitors-and-leads/output/phase1_competitors_context.json` with one entry per client containing the SerpAPI organic results for the query `"<client> APAC competitors direct"`.

### Step 3 — Reasoning (you, Claude, do this)

Read the JSON. For each client, apply the prompts in `~/.claude/competitors-and-leads/lib/prompts.py` (`PHASE1_SYSTEM` + `PHASE1_USER_TEMPLATE`) — copied verbatim from n8n node `p1-agent`. For each client, output 5–10 APAC competitors with:

- competitor_name
- industry
- website (must be real and verifiable)
- why_competitor

Hard rules: only include verifiable APAC competitors; never fabricate names or websites; if you cannot find any, return an empty list for that client.

For batches over 5 clients, delegate the per-client extraction to Explore subagents in parallel — one agent per client, each given that client's search results and asked to return JSON. Save the merged output to `~/.claude/competitors-and-leads/output/phase1_drafts.json` shaped like:

```json
{
  "competitors": [
    {
      "Client Company": "<client name>",
      "Competitor Name": "...",
      "Industry": "...",
      "Website URL": "...",
      "Why Competitor": "...",
      "Status": "new"
    }
  ]
}
```

### Step 4 — Show your work and ask before writing

Print a per-client tally (e.g. "Samsung: 6 competitors, AWS: 8, ..."). Ask the user to confirm before the write.

### Step 5 — Write to the sheet

```
python ~/.claude/competitors-and-leads/run.py phase1-write --input ~/.claude/competitors-and-leads/output/phase1_drafts.json
```

This appends new rows to the Competitors tab (idempotent — rows already present are skipped) and flips `SBR.Checked = Yes` for clients that just got new competitor rows.

## Verification

After writing, re-run `phase1-collect --dry-run`. The candidate count should drop by the number of clients you just processed.

## Notes

- Sheet ID and SA path are configured in `~/.claude/competitors-and-leads/secrets/api_keys.json`.
- The n8n workflow uses GPT-4o-mini for this step. We use Claude. Quality is generally higher; outputs may differ in wording but follow the same JSON schema.
- If a SerpAPI call fails, the per-client search_results array is empty but the candidate stays in the JSON. You can still produce competitors for it from training knowledge if confident, but err toward empty rather than fabricating.
