---
name: sales-research-competitor
description: Research recent activity (2025+) for every Competitor whose POCs lack research data. Runs two SerpAPI searches per competitor (product launches/funding/expansion, executives/leadership/partnerships) and Claude generates recent_activity + collaboration_opportunities + summary with a B2B reframe. Updates the POCs tab so all POCs of that competitor share the same research fields. Mirrors Phase 3 of the n8n 'Sales - Competitors and Leads' workflow. Use when the user asks to research competitors, generate B2B angles, /sales-research-competitor, or fill in Recent Activity / Suggested Collaborations.
---

# /sales-research-competitor

Phase 3 of the competitors-and-leads pipeline. Generates the `Website Research Summary`, `Recent Activity`, `Suggested Collaborations`, and `Research Sources` fields used by Phase 4 email drafting.

## Runbook

### Step 1 — Dry-run candidate count

```
python ~/.claude/competitors-and-leads/run.py phase3-collect --dry-run
```

A "candidate" is any competitor whose Status is `pocs_found` and whose POC rows have an empty `Website Research Summary`. Two SerpAPI calls per candidate.

### Step 2 — Collect search results

```
python ~/.claude/competitors-and-leads/run.py phase3-collect
```

Writes `~/.claude/competitors-and-leads/output/phase3_research_context.json`. Each candidate block contains two `searches` (one for product/funding/expansion, one for executives/partnerships) with the SerpAPI organic results.

### Step 3 — Reasoning (you, Claude)

Apply the prompts in `~/.claude/competitors-and-leads/lib/prompts.py` (`PHASE3_SYSTEM` + `PHASE3_USER_TEMPLATE`) — copied from n8n node `p2-research-agent`. Pass today's date into the system prompt's `{today}` placeholder.

**The B2B reframing rule is critical.** CMG's audience is B2B executives. If the recent activity is mostly B2C (consumer launches, retail campaigns, lifestyle), pivot to a B2B anchor:
- Reframe through a B2B lens (supply-chain, market-entry strategy, leadership behind the launch, regional expansion)
- OR surface a different, more B2B-friendly anchor (funding, leadership hire, partnership, ESG move, earnings)
- OR propose a NEW angle (thought-leadership topic the company's execs could speak to)

Each `collaboration_opportunities` entry MUST include a `b2b_angle` field.

For batches over 5 candidates, delegate per-competitor reasoning to Explore subagents in parallel.

Save results keyed by lowercased competitor name (so the writer can fan it out across all POC rows of that competitor):

```json
{
  "competitor name lowercase": {
    "website_research_summary": "Brief summary, with explicit B2B pivot if pivoting from B2C",
    "recent_activity": "[PRODUCT LAUNCH] (date) ...\n[EVENT] (date) ...",
    "suggested_collaborations": "[EVENT] suggestion. Rationale: ... B2B angle: ...",
    "research_sources": "url1\nurl2\nurl3"
  }
}
```

The `recent_activity` and `suggested_collaborations` strings should join entries with `\n` — that's how the n8n workflow stores them and what Phase 4's drafting prompt consumes.

Output file: `~/.claude/competitors-and-leads/output/phase3_drafts.json` with the dict shape above (no top-level wrapper).

### Step 4 — Write to the sheet

```
python ~/.claude/competitors-and-leads/run.py phase3-write --input ~/.claude/competitors-and-leads/output/phase3_drafts.json
```

Updates EVERY POC row of each competitor in the dict. The same research fields are duplicated across all POC rows of that competitor (matches the existing schema; the n8n workflow does the same).

## Verification

`phase3-collect --dry-run` should now exclude the competitors you just researched.

## Notes

- The n8n agent caps SerpAPI at 2 searches per competitor. We don't enforce that in Python — but the prompt does, so the LLM will respect it.
- ONLY include activity from 2025 onward. Anything older is ignored even if it appears in search results.
- If absolutely no B2B-relevant activity exists, the prompt allows you to propose a thought-leadership angle instead of fabricating activities.
