---
name: sales-pipeline-all
description: Run the full competitors-and-leads pipeline end-to-end across all unprocessed records. Phase 1 (find competitors) → Phase 2 (find POCs) → Phase 3 (research recent activity) → Phase 4 (draft emails). Each phase pauses with a candidate-count summary so the user can stop or scope before high-cost API runs. Use when the user asks to run the whole pipeline, /sales-pipeline-all, full sales prospecting run, or do everything at once.
---

# /sales-pipeline-all

Runs all four phases of the competitors-and-leads pipeline in order, with a confirmation gate before each one.

## Runbook

For each phase below, do the dry-run first, surface the candidate count to the user, and **wait for confirmation** before continuing. Phases 2 and 4 in particular are high-cost (Apify and per-POC drafting), so it's important the user sees the scale before each.

### Phase 1 — Find Competitors

Follow the runbook in `~/.claude/skills/sales-find-competitors/SKILL.md`. After it finishes, summarize what landed (rows added to Competitors, clients flipped to Checked='Yes').

### Phase 2 — Find POCs

Follow the runbook in `~/.claude/skills/sales-find-pocs/SKILL.md`. Apify steps can take 1–2 minutes per competitor — warn the user if there are more than 5 candidates.

### Phase 3 — Research Competitors

Follow the runbook in `~/.claude/skills/sales-research-competitor/SKILL.md`.

### Phase 4 — Draft Emails

Follow the runbook in `~/.claude/skills/sales-draft-emails/SKILL.md`.

### Final summary

Print a tally:
- Competitors added (Phase 1)
- POCs added (Phase 2)
- POC rows updated with research (Phase 3)
- Email Drafts appended (Phase 4)
- Status flips made

## Stopping early

If the user wants to stop after a particular phase, exit cleanly. The next time they run `/sales-pipeline-all` it'll pick up where it left off (each phase's "list_candidates" already filters out completed records).

## Notes

- This is just orchestration — all the real logic lives in the per-phase skills. If a phase fails, fix it in the per-phase runbook, not here.
- The pipeline is NOT parallel across phases. Phase N depends on Phase N-1's writes landing in the sheet first.
- Within a phase, batch reasoning across multiple records can be parallelized via Explore subagents (see each phase's SKILL.md).
