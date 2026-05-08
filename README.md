# CMG Claude Skills

Claude Code skills for the Charlton Media Group editorial, commercial, and social-distribution workflows. Each subfolder is a self-contained bundle that wires Claude Code to a real, repeatable team task — generating Earned Media Reports, drafting C-suite discussion topics for the [2026] sheet, or auditing IF/EXCLUSIVE article distribution across the 20 publication social accounts.

## What's in here

| Bundle | Skill(s) | Purpose | Packaging |
|---|---|---|---|
| [`EMR/`](EMR/README.md) | `/charlton-earned-media-report` | Generate an Earned Media Report DOCX for a brand by scraping any/all of five Charlton B2B publications (SBR, HKB, ABF, ABR, RA). | Workspace |
| [`Editorial/`](Editorial/README.md) | `/editorial-video-researcher` | AI-draft discussion topics + 5 C-suite questions per article and append to the `[2026] Discussion Topic` Google Sheet tab. | Workspace |
| [`TDM-EMR/`](TDM-EMR/README.md) | `/earned-media-report` | Same as EMR but for Travel Daily Media (hospitality/travel brands). | Workspace |
| [`SocPi/`](SocPi/README.md) | `/if-exclusives-audit`, `/if-exclusives-audit-quick` | Audit IF/EXCLUSIVE article distribution across 20 publications × Facebook/Instagram/LinkedIn/X via SocialPilot, write results back to the *Commercial SocPi - Links* sheet. | User skill |
| [`Sales/competitors-and-leads/`](Sales/competitors-and-leads/README.md) | `/sales-find-competitors`, `/sales-find-pocs`, `/sales-research-competitor`, `/sales-draft-emails`, `/sales-pipeline-all` | Five-phase sales prospecting pipeline ported from the n8n *Sales - Competitors and Leads* workflow. Finds competitors → POCs → researches → drafts personalized B2B emails into the *Existing Clients (2021 to 2025)* sheet. | User skills (5) sharing one bundle |

## Installation

If you're a human, the manual `cp` / `Copy-Item` snippet under [Two packaging patterns](#two-packaging-patterns-both-supported) is the short version. If you're letting Claude Code do the install, just say something like:

> *"Install the skills from this repo."*

Claude will read this section (and [`CLAUDE.md`](CLAUDE.md)) as a runbook and execute every step that doesn't require credentials or settings access — including any `pip install`. You only have to do four things by hand: drop in a Google SA key, configure MCP connectors, install the `anthropic-skills` plugin, and restart Claude Code. The exact playbook an agent follows:

### Step 1 — Detect runtimes (must pass before anything else runs)

The agent verifies the colleague's machine has the runtimes the skills need. Both are quick installs from official sources, but the agent does **not** install them — it just checks and stops if missing.

- **Python ≥ 3.10** (used by SocPi and Editorial). If missing, install from <https://www.python.org/downloads/>. On Windows, tick "Add Python to PATH" during install.
- **Node ≥ 18** (used by EMR and TDM-EMR scrapers — built-in `fetch` requires v18). If missing, install from <https://nodejs.org/> (LTS).

If either is missing, the agent surfaces a friendly message and stops. Re-run the install request once the runtime is on PATH.

### Step 2 — Install SocPi user skills

Copy these two folders verbatim into the user's home `.claude/skills/` directory. The agent creates the directory if it doesn't exist.

| Source (in this repo) | Destination |
|---|---|
| `SocPi/if-exclusives-audit/` | `~/.claude/skills/if-exclusives-audit/` (Windows: `%USERPROFILE%\.claude\skills\if-exclusives-audit\`) |
| `SocPi/if-exclusives-audit-quick/` | `~/.claude/skills/if-exclusives-audit-quick/` |

The agent uses `cp -r` on POSIX, `Copy-Item -Recurse` on PowerShell, or `xcopy /E /I` on cmd. The folder names at the destination **must** stay exactly `if-exclusives-audit` and `if-exclusives-audit-quick` — they have to match the `name:` field inside each `SKILL.md`.

If a destination folder already exists, the agent **stops and asks** before overwriting — the existing copy may have your real `secrets/gsheets-sa.json` and local edits. Nothing is overwritten without explicit confirmation.

A short SocPi-specific runbook lives at [`SocPi/INSTALL.md`](SocPi/INSTALL.md).

### Step 2b — Install Sales user skills (only if you asked for Sales)

The Sales bundle is **two-target**: the orchestration code lives at `~/.claude/competitors-and-leads/`, and the 5 thin SKILL.md folders go to `~/.claude/skills/`. The agent only runs this step if the user mentioned "sales", "competitors and leads", or one of the `/sales-*` commands.

| Source (in this repo) | Destination |
|---|---|
| `Sales/competitors-and-leads/` | `~/.claude/competitors-and-leads/` |
| `Sales/competitors-and-leads/skills/sales-find-competitors/` | `~/.claude/skills/sales-find-competitors/` |
| `Sales/competitors-and-leads/skills/sales-find-pocs/` | `~/.claude/skills/sales-find-pocs/` |
| `Sales/competitors-and-leads/skills/sales-research-competitor/` | `~/.claude/skills/sales-research-competitor/` |
| `Sales/competitors-and-leads/skills/sales-draft-emails/` | `~/.claude/skills/sales-draft-emails/` |
| `Sales/competitors-and-leads/skills/sales-pipeline-all/` | `~/.claude/skills/sales-pipeline-all/` |

Same overwrite policy — the agent stops and asks if any destination already exists. Detailed step-by-step (with PowerShell + POSIX commands) is in [`Sales/competitors-and-leads/INSTALL.md`](Sales/competitors-and-leads/INSTALL.md).

### Step 3 — Auto-install Python dependencies

The agent runs `pip install` for you. No manual command needed.

```bash
# SocPi (run after Step 2 succeeds)
python -m pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt

# Editorial (run if you said "install everything" or specifically asked for Editorial)
python -m pip install -r Editorial/.claude/skills/editorial-video-researcher/requirements.txt

# Sales (run only if Step 2b ran)
python -m pip install -r ~/.claude/competitors-and-leads/requirements.txt
```

If pip fails with a permissions error on a locked-down Windows machine, the agent retries with `--user`. EMR and TDM-EMR have zero Node dependencies — no `npm install` step.

### Step 4 — Do NOT copy the workspace skills

`EMR/`, `Editorial/`, and `TDM-EMR/` are workspace skills, not user skills. They are invoked by `cd`-ing into their bundle folder and running `claude` — there is nothing to copy. The agent leaves them in place inside the cloned repo.

### Step 5 — The four remaining manual steps

After Steps 2 and 3 land, the agent surfaces these — they involve credentials, OAuth, or a Claude Code restart, so the agent cannot do them for you:

1. **Drop a Google service-account key** at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json` (and at `Editorial/.claude/skills/editorial-video-researcher/secrets/gsheets-sa.json` if you'll use Editorial). There is a `gsheets-sa.json.example` next to each as a template. Setup walkthrough: [Setting up the Google service account](#setting-up-the-google-service-account-one-time). The Sales bundle reuses this same SocPi key by default.
2. **Configure MCP connectors** (Google Drive + SocialPilot) in Claude Code. The OAuth flow happens in Claude Code's settings panel. Details: [MCP connectors](#mcp-connectors).
3. **Install the `anthropic-skills` plugin** in Claude Code (Settings → Plugins). Used by EMR/TDM-EMR for DOCX rendering and PDF reading.
4. **For Sales only — populate `~/.claude/competitors-and-leads/secrets/api_keys.json`** with SerpAPI / Tavily / Apify / Hunter keys. The example file lists where to find each in the n8n workflow. See [`Sales/competitors-and-leads/INSTALL.md`](Sales/competitors-and-leads/INSTALL.md) Step 4.
5. **Restart Claude Code** so the newly installed skills are picked up. Until you restart, `/if-exclusives-audit`, `/sales-*`, etc. will not appear under `/`.

### Step 6 — If you want to use a workspace skill (EMR / Editorial / TDM-EMR)

Just `cd` into that bundle and run `claude` from there:

```bash
cd EMR        # or Editorial, or TDM-EMR
claude
```

The skill is auto-discovered from `<bundle>/.claude/skills/<name>/SKILL.md`. No install step — the workspace folder is the install. (Editorial still needs its Python deps from Step 3 and an SA key from Step 5.1; TDM-EMR additionally needs `Media Kit.pdf` for the Recommendations section.)

---

## Two packaging patterns, both supported

The bundles use whichever pattern fits best — there's no need to standardize.

**Workspace** (EMR, Editorial, TDM-EMR). The folder *is* the project. Open Claude Code inside it and the skill is auto-discovered:

```bash
cd EMR        # or Editorial, or TDM-EMR
claude
# then in the Claude Code prompt:
/charlton-earned-media-report SBR DBS
```

The skill's SKILL.md lives at `<bundle>/.claude/skills/<skill-name>/`. Scripts, output folders, and reference assets sit alongside it in the workspace, which is what lets the SKILL.md reference `Minor Hotels — Earned Media Report.pdf` and write to `output/<ACRONYM>/<brand>.docx` with simple relative paths.

**User skill** (SocPi). The folder is meant to be installed into your Claude Code user-skills directory, after which the slash command works from anywhere on disk:

```bash
# Windows
cp -r SocPi/if-exclusives-audit       "$USERPROFILE/.claude/skills/"
cp -r SocPi/if-exclusives-audit-quick "$USERPROFILE/.claude/skills/"

# macOS / Linux
cp -r SocPi/if-exclusives-audit       ~/.claude/skills/
cp -r SocPi/if-exclusives-audit-quick ~/.claude/skills/
```

`/if-exclusives-audit-quick` is a thin companion to `/if-exclusives-audit` — install both, since the quick variant calls into the main skill's scripts and secrets.

## Prerequisites

Before any bundle will run, you need:

### Runtimes

- **Claude Code** ([install instructions](https://docs.claude.com/en/docs/claude-code)). Each bundle's README lists the slash command to invoke.
- **Node.js 18+** on PATH — used by EMR and TDM-EMR scrapers (built-in `fetch`). Zero `npm install` required; both scrapers are dependency-free.
- **Python 3.10+** on PATH — used by Editorial and SocPi. The agent install playbook (see [Installation](#installation)) auto-runs `pip install` for both, so you don't need to do this by hand. If you're installing manually:
  - SocPi: `python -m pip install -r SocPi/if-exclusives-audit/requirements.txt`
  - Editorial: `python -m pip install -r Editorial/.claude/skills/editorial-video-researcher/requirements.txt`

### Required Anthropic skills (DOCX rendering, PDF reading)

EMR and TDM-EMR both delegate parts of their pipeline to skills bundled in Anthropic's official catalog:

| Skill | Used by | What it does |
|---|---|---|
| `anthropic-skills:docx` | EMR, TDM-EMR | Renders the final Earned Media Report as a `.docx` file. |
| `anthropic-skills:pdf-reader` | TDM-EMR (and useful for EMR Media Kits) | Reads the TDM Media Kit so the Recommendations section can name specific products and prices. |

Install the `anthropic-skills` plugin in Claude Code so both are available — your settings panel (Settings → Plugins or Skills) is the canonical place to add it. If a clone is missing these, the EMR/TDM-EMR pipelines will run up to the rendering step and then stall.

### MCP connectors

Editorial and SocPi each rely on MCP servers configured in Claude Code. The skill code addresses tools by suffix (e.g. `__DeliveredPosts`, `__download_file_content`), so the per-machine MCP server ID prefix can differ — you don't need to match the original install.

| Connector | Used by | Tools the skills call | Auth note |
|---|---|---|---|
| **Google Drive** | Editorial, SocPi | `download_file_content` | OAuth-authenticated Google account that has at least read access to the target sheet. |
| **SocialPilot** | SocPi | `DeliveredPosts`, `QueuedPosts`, `GroupList`, `AccountList`, `UserInfo` | API token from the SocialPilot account that owns the 20 publication social profiles. |

Add MCP servers via Claude Code's settings panel or the `claude mcp` CLI (run `claude mcp --help` for the exact subcommand on your version). Anthropic's MCP docs walk through the flow: <https://docs.claude.com/en/docs/claude-code/mcp>. After installing, run `/help` in Claude Code or open the connector list to confirm the tool names above are present.

## First-run setup per bundle

Each bundle's README has the full runbook. The condensed version:

### EMR (`charlton-earned-media-report`)

1. `cd EMR && claude`
2. (Optional) Drop the five `<ACRONYM> Media Kit.pdf` files in `EMR/` if you have them — they're flagged "reference only" by the runtime, but useful for the team. Source: internal Drive (gitignored, not in this repo).
3. In Claude Code: `/charlton-earned-media-report SBR DBS` (single-pub) or `/charlton-earned-media-report DBS` (all five → combined master report).

### Editorial (`editorial-video-researcher`)

1. Create a Google Cloud service account, generate a JSON key, and share the *Copy of 2025-2026 Asian Business Media* sheet with that SA email as **Editor**.
2. Drop the JSON key into `Editorial/.claude/skills/editorial-video-researcher/secrets/gsheets-sa.json` (gitignored automatically — the `.example` next to it is the template).
3. `cd Editorial && claude`, then `/editorial-video-researcher SBR=2 HKB=1`.

### TDM-EMR (`earned-media-report`)

1. **Place `TDM-EMR/Media Kit.pdf` in the folder** — required for Step 4.5 of the SKILL.md, which reads it so the Recommendations section can name specific TDM products and prices. Gitignored (it's a licensed product catalog), so source it from the team's internal Drive on each new machine. Without it, the report still renders but the Recommendations section will be generic and won't quote prices.
2. `cd TDM-EMR && claude`, then `/earned-media-report Hilton`.

### SocPi (`if-exclusives-audit` + `-quick`)

1. Install both folders into `~/.claude/skills/` (see snippet above).
2. Configure the **SocialPilot** and **Google Drive** MCP connectors in Claude Code. The SocialPilot account must own the 20 publication social profiles.
3. Use the same SA key as Editorial (or a separate one). Share the *Commercial SocPi - Links* sheet (`1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`) with the SA email as **Editor**. Drop the JSON into `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`.
4. `pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt`.
5. From any folder: `/if-exclusives-audit`.

### Sales (`sales-find-competitors`, `sales-find-pocs`, `sales-research-competitor`, `sales-draft-emails`, `sales-pipeline-all`)

1. Two-target install — copy `Sales/competitors-and-leads/` to `~/.claude/competitors-and-leads/`, then copy the 5 thin SKILL.md folders under `Sales/competitors-and-leads/skills/` into `~/.claude/skills/`. Step-by-step in [`Sales/competitors-and-leads/INSTALL.md`](Sales/competitors-and-leads/INSTALL.md).
2. `pip install -r ~/.claude/competitors-and-leads/requirements.txt`.
3. Reuses the SocPi SA key by default. Share the *Existing Clients (2021 to 2025)* sheet with that SA email as **Editor**.
4. Populate `~/.claude/competitors-and-leads/secrets/api_keys.json` with SerpAPI / Tavily / Apify / Hunter keys (template at `api_keys.json.example`; locations in the n8n workflow listed in the INSTALL.md table).
5. Smoke-test each phase with `--dry-run` (no external API calls). Then from any folder: `/sales-pipeline-all` or any of the per-phase commands.

## Setting up the Google service account (one-time)

The same SA key can drive both Editorial and SocPi:

1. **Create the SA**: Google Cloud Console → IAM & Admin → Service Accounts → Create. No project roles needed (Sheets access is granted per-sheet).
2. **Generate a JSON key**: Keys → Add key → JSON. Download.
3. **Share the sheets**: open each target sheet → Share → paste the SA's `client_email` (e.g. `something@something.iam.gserviceaccount.com`) → set role to **Editor**.
   - Editorial: *Copy of 2025-2026 Asian Business Media* (file ID `1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU`)
   - SocPi: *Commercial SocPi - Links* (file ID `1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`)
4. **Drop the JSON** into the matching `secrets/` folder using the filename `gsheets-sa.json`. The top-level `.gitignore` keeps it out of git.

## What's gitignored

The top-level [`.gitignore`](.gitignore) covers all four bundles. The short version:

- All `secrets/*.json` (real keys stay on disk; only `.example` skeletons are committed).
- All run outputs and per-brand caches (regenerated on every run).
- The five Media Kit PDFs and `TDM-EMR/Media Kit.pdf` (large, "reference only", gitignored to keep the repo lean — `Minor Hotels — Earned Media Report.pdf` is committed because the SKILL.md actively references it for report structure).
- Editorial's `xml_feeds/*.xml` dumps (refetched each run).
- Standard Python/Node/OS junk.

## Repository layout

```
.
├── README.md                                    ← you are here
├── .gitignore
├── Install-Claude-Skills-Guide.docx             ← end-user-facing setup guide (kept as-is)
├── EMR/                                         ← workspace skill
│   ├── README.md
│   ├── Minor Hotels — Earned Media Report.pdf   ← report-structure reference
│   ├── thought-leader-package-prices.md
│   ├── scripts/charlton-emr.mjs
│   ├── scripts/render-docx.py
│   ├── output/                                  ← run outputs (gitignored)
│   └── .claude/skills/charlton-earned-media-report/SKILL.md
├── Editorial/                                   ← workspace skill
│   ├── README.md
│   ├── xml_feeds/                               ← runtime feed dumps (gitignored)
│   └── .claude/skills/editorial-video-researcher/
│       ├── SKILL.md
│       ├── config.yaml
│       ├── scripts/{fetch_article,fetch_feed,sheet_*}.py
│       └── secrets/                             ← drop SA key here (gitignored)
├── TDM-EMR/                                     ← workspace skill
│   ├── README.md
│   ├── Minor Hotels — Earned Media Report.pdf   ← report-structure reference
│   ├── scripts/earned-media-report.mjs
│   ├── output/                                  ← run outputs (gitignored)
│   └── .claude/skills/earned-media-report/SKILL.md
├── SocPi/                                       ← user skills (install to ~/.claude/skills/)
│   ├── README.md, INSTALL.md
│   ├── if-exclusives-audit/
│   │   ├── SKILL.md, README.md, config.yaml, requirements.txt
│   │   ├── scripts/*.py
│   │   ├── cache/, runs/                        ← per-run scratch (gitignored)
│   │   └── secrets/                             ← drop SA key here (gitignored)
│   └── if-exclusives-audit-quick/
│       ├── SKILL.md, README.md
│       └── (no scripts — piggybacks on the main skill)
└── Sales/competitors-and-leads/                 ← bundle: code → ~/.claude/competitors-and-leads/
    ├── INSTALL.md, README.md
    ├── run.py, requirements.txt
    ├── lib/                                     ← phase modules + platform adapters
    ├── output/                                  ← per-phase JSON intermediates (gitignored)
    ├── secrets/                                 ← drop api_keys.json here (gitignored)
    └── skills/sales-{find-competitors,find-pocs,research-competitor,draft-emails,pipeline-all}/
                                                  ← thin SKILL.md folders → ~/.claude/skills/
```

## End-user installation guide

For non-engineers on the team, [`Install-Claude-Skills-Guide.docx`](Install-Claude-Skills-Guide.docx) walks through the same setup with screenshots. Engineers should prefer this README.
