# Competitors and Leads — Claude Code skill bundle

Five-phase sales prospecting pipeline ported from the n8n workflow
[Sales - Competitors and Leads](https://n8n.charltonmedia.com/workflow/2HDVb6rOZZsV7NMg).
Each phase is a separate slash command in Claude Code, plus an orchestrator
that runs all four end-to-end.

## What it does

Reads the `Existing Clients (2021 to 2025)` Google Sheet and, for every
unprocessed row, fans out into:

1. **`/sales-find-competitors`** — finds 5–10 APAC competitors per client → Competitors tab
2. **`/sales-find-pocs`** — finds marketing/comms POCs per competitor (Tavily + Apify + Hunter.io) → POCs tab
3. **`/sales-research-competitor`** — researches recent activity (2025+) with B2B reframe → POCs tab fields
4. **`/sales-draft-emails`** — drafts personalized outreach emails matching the team's Revised Version tone → Email Drafts tab
5. **`/sales-pipeline-all`** — runs 1→2→3→4 sequentially with a confirmation gate before each phase

## Architecture

```
~/.claude/competitors-and-leads/         ← real code (this bundle, copied here on install)
├── lib/
│   ├── auth.py                          ← gspread auth + secrets loader
│   ├── sheets.py                        ← read/write helpers per tab
│   ├── prompts.py                       ← n8n prompts copied verbatim + Revised Version exemplars
│   ├── platforms/
│   │   ├── serpapi.py
│   │   ├── tavily.py
│   │   ├── apify.py
│   │   └── hunter.py
│   ├── phase1_competitors.py            ← collect SerpAPI search results
│   ├── phase2_pocs.py                   ← collect Tavily + Apify + Hunter
│   ├── phase3_research.py               ← collect SerpAPI for recent activity
│   ├── phase4_drafts.py                 ← collect drafting context (migrated pilot)
│   └── writers.py                       ← all four phases' write paths
├── secrets/
│   ├── api_keys.json                    ← user-populated, gitignored
│   └── api_keys.json.example
├── output/                              ← per-run JSON artefacts (gitignored)
├── requirements.txt
└── run.py                               ← single CLI: python run.py phase<N>-(collect|write)

~/.claude/skills/                        ← thin slash-command wrappers
├── sales-find-competitors/SKILL.md
├── sales-find-pocs/SKILL.md
├── sales-research-competitor/SKILL.md
├── sales-draft-emails/SKILL.md
└── sales-pipeline-all/SKILL.md
```

Each `SKILL.md` is a runbook telling Claude how to chain `run.py phaseN-collect`
→ LLM reasoning → `run.py phaseN-write`. The reasoning step happens in the
Claude Code conversation, not in a script — that's how we avoid an OpenAI key.

## Install

See [INSTALL.md](INSTALL.md). The repo's top-level `CLAUDE.md` also references
this bundle in its install playbook so any agent that lands here knows
how to set it up.

## Phase-by-phase reference

### Phase 1 — Find Competitors

| | |
|---|---|
| **Slash** | `/sales-find-competitors` |
| **Inputs** | `SBR` tab rows where `Checked != 'Yes'` |
| **External calls** | SerpAPI (1 search per client) |
| **LLM step** | `PHASE1_SYSTEM` + `PHASE1_USER_TEMPLATE` (n8n `p1-agent`) |
| **Outputs** | Rows appended to `Competitors`; `SBR.Checked = 'Yes'` |
| **n8n parity** | Direct port of `p1-*` nodes |

### Phase 2 — Find POCs

| | |
|---|---|
| **Slash** | `/sales-find-pocs` |
| **Inputs** | `Competitors` tab rows where `Status` ∉ `{pocs_found, no_pocs, email_drafted}` |
| **External calls** | Tavily ×3 (LinkedIn URL, team page, contacts), Apify ×2 (employees, profiles+emails), Hunter.io ×1 (domain) |
| **LLM step** | `PHASE2_EXTRACT_USER_TEMPLATE` (n8n `p2-extract-pocs-ai`) |
| **Outputs** | Rows appended to `POCs`; `Competitor.Status = 'pocs_found'` or `'no_pocs'` |
| **n8n parity** | Direct port of `p2-tavily-*`, `p2-apify*`, `p2-hunter`, `p2-extract-pocs-ai` |

### Phase 3 — Research Competitor

| | |
|---|---|
| **Slash** | `/sales-research-competitor` |
| **Inputs** | `Competitors` rows with `Status='pocs_found'` whose POCs have empty `Website Research Summary` |
| **External calls** | SerpAPI ×2 (product/funding, leadership/partnerships) |
| **LLM step** | `PHASE3_SYSTEM` + `PHASE3_USER_TEMPLATE` (n8n `p2-research-agent`) — B2B reframe |
| **Outputs** | All POCs of the competitor get `Website Research Summary`, `Recent Activity`, `Suggested Collaborations`, `Research Sources` filled |
| **n8n parity** | Direct port of `p2-research-agent` |

### Phase 4 — Draft Emails

| | |
|---|---|
| **Slash** | `/sales-draft-emails` |
| **Inputs** | `POCs` rows with `Status='new'`, valid email, not in Email Drafts |
| **External calls** | None (all data already in sheet) |
| **LLM step** | `PHASE4_SYSTEM` (with 3 Revised Version exemplars) + `PHASE4_USER_TEMPLATE` (n8n `p2-draft-email`) |
| **Outputs** | Rows appended to `Email Drafts`; `POCs.Status='email_drafted'`; `Competitor.Status='pocs_found'` |
| **n8n parity** | Direct port of `p2-select-kits` + `p2-draft-email` + `p2-parse-email`, with tighter tone via Revised Version exemplars |

## Differences from the n8n workflow

| Aspect | n8n | This skill |
|---|---|---|
| LLM | GPT-4o-mini (OpenAI API) | Claude (the harness running this skill) |
| Trigger | Manual or scheduled, runs autonomously | User runs a slash command per phase |
| Skip logic | `Checked` column with today's date | `Status`/`Checked` filled = skip |
| Tone | n8n agent's default | Revised Version exemplars baked into prompt |
| Per-target arg | n/a (always batches) | n/a (batch only in v1; per-target later) |

## Outputs are JSON intermediates

Each phase produces two JSON files in `~/.claude/competitors-and-leads/output/`:
- `phaseN_<name>_context.json` — raw API results, written by `phaseN-collect`
- `phaseN_drafts.json` — Claude's reasoning output, then consumed by `phaseN-write`

You can resume mid-phase by editing the JSON and re-running the write step.
The writer is idempotent — re-runs append zero rows if everything is already
there.

## Concurrency with the live n8n workflow

The n8n workflow runs against the same sheet. If both try to write to the
same `(Competitor Name, POC Name)` pair, the writer's skip-set check
prevents duplicates. To be safe, **pause the n8n workflow during a skill
run**.
