---
name: sales-draft-emails
description: Draft personalized B2B outreach emails for every POC in the POCs tab whose Status='new' and Email is real (not 'email not found') and isn't already in the Email Drafts tab. Matches the tightened Revised Version tone the team has been using (~80–110 words body, observational opener, named publications, "Best regards," sig). Appends drafts to Email Drafts tab and flips POCs.Status to 'email_drafted'. Mirrors Phase 4 of the n8n 'Sales - Competitors and Leads' workflow. Use when the user asks to draft emails, write outreach, /sales-draft-emails, or generate emails for the marketing POCs.
---

# /sales-draft-emails

Phase 4 of the competitors-and-leads pipeline. Drafts personalized outreach emails for every undrafted POC and writes them to the Email Drafts tab.

## Runbook

### Step 1 — Dry-run candidate count

```
python ~/.claude/competitors-and-leads/run.py phase4-collect --dry-run
```

Prints total POC candidates plus a per-competitor breakdown. **Always confirm with the user** before drafting more than ~10 emails — the user may want to scope by competitor first.

### Step 2 — Collect drafting context

```
python ~/.claude/competitors-and-leads/run.py phase4-collect
```

Writes `~/.claude/competitors-and-leads/output/phase4_drafts_context.json`. Each entry contains: POC row data, the matched media kits (scored per the n8n `p2-select-kits` algorithm), and the `matched_publications_string`.

### Step 3 — Reasoning (you, Claude)

Read the JSON. Group POCs by competitor (the same company-level research applies to all POCs of that competitor; only the greeting + opening line + one talking point should differ).

Apply the prompts in `~/.claude/competitors-and-leads/lib/prompts.py` (`PHASE4_SYSTEM` + `PHASE4_USER_TEMPLATE`) — copied from n8n nodes `p2-draft-email` and `p2-parse-email`. The system prompt is augmented with three Revised Version exemplars from the live sheet so the tone matches what the team actually uses.

**Hard tone constraints (from the exemplars):**
- 80–110 words body (NOT 100–150 — the team prefers tighter)
- Open with "I noticed…" / "I've been following…" — observational, specific, NOT "I hope this message finds you well"
- Reference 2–3 publications by name (Singapore Business Review, Asian Business Review, Hong Kong Business, Travel Daily Media — pick what's editorially right for the sector, even if the algorithmic match scored 0)
- ONE collaboration idea, max two. No pricing.
- Sign-off "Best regards," + 3-line signature: `[Your Name]` / `[Your Position]` / `Charlton Media Group`
- NO em-dashes (—). Use commas, short sentences, or `--` (double-hyphen).
- First person ("I" / "we"), not corporate voice.

For each POC, output JSON matching the Email Drafts tab schema:

```json
{
  "Client Company": "...",
  "Competitor Name": "...",
  "POC Name": "...",
  "POC Email": "...",
  "POC Title": "...",
  "Email Subject": "...",
  "Email Body": "Hi <Name>,\n\n<body>\n\nBest regards,\n[Your Name]\n[Your Position]\nCharlton Media Group",
  "Key Talking Points": "point1; point2; point3",
  "Matched Publications": "Singapore Business Review, Asian Business Review, ...",
  "Status": "draft",
  "Created Date": "<today>"
}
```

For batches over 5 POCs, delegate per-competitor batch drafting to Explore subagents in parallel.

Save the array to `~/.claude/competitors-and-leads/output/phase4_drafts.json`:

```json
{ "drafts": [{...}, {...}] }
```

### Step 4 — Show samples + ask before writing

For each competitor, print 1 sample draft (subject + body). Ask the user to confirm the tone matches the Revised Version style. If they want revisions, do them inline before writing.

### Step 5 — Write to the sheet

```
python ~/.claude/competitors-and-leads/run.py phase4-write --input ~/.claude/competitors-and-leads/output/phase4_drafts.json
```

Appends rows to Email Drafts (idempotent, skip-set check on Competitor + POC Name), flips POCs.Status='email_drafted', flips Competitor.Status='pocs_found' for any competitor that wasn't already.

## Verification

After writing:
1. `python ~/.claude/competitors-and-leads/run.py drafts-status` should show fewer remaining candidates
2. Open the Email Drafts tab and spot-check 2–3 random rows for tone match

## Tone-refresh

If the team adds more Revised Versions to the sheet over time, refresh the exemplars used in the prompt:

```
python ~/.claude/competitors-and-leads/run.py drafts-tone-examples
```

This pulls the latest revised drafts to `output/revised_examples.json` so a future iteration can update `lib/prompts.py:REVISED_TONE_EXEMPLARS`.
