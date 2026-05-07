# CLAUDE.md — Project context for Claude Code

This file tells any Claude Code agent that lands in this repo how to work with it. It is consulted automatically when Claude Code starts here.

## What this repo is

Four Claude Code skill bundles for Charlton Media Group:

- `EMR/` — `/charlton-earned-media-report` (workspace skill)
- `Editorial/` — `/editorial-video-researcher` (workspace skill)
- `TDM-EMR/` — `/earned-media-report` (workspace skill)
- `SocPi/if-exclusives-audit/` and `SocPi/if-exclusives-audit-quick/` (user skills)

Full docs are in [README.md](README.md). This file is the short, agent-facing version.

## When the user asks you to install these skills

Trigger phrases: *"install the skills"*, *"install this repo's skills"*, *"set up these skills"*, *"add these to my Claude Code"*, or anything semantically equivalent.

### Run this playbook in order

The goal is that the user types one sentence and Claude does every step that doesn't require credentials or Claude Code settings access. Follow each step in order — do not skip ahead.

#### Step 1 — Confirm cwd and detect runtimes

**1a. Working directory.** If `pwd` / `Get-Location` is not the repo root (the folder containing this `CLAUDE.md`), `cd` there first or ask the user where they cloned it.

**1b. Python ≥ 3.10.** Required by SocPi and Editorial.

- POSIX: `python3 --version` (fall back to `python --version`)
- PowerShell: `python --version`

If missing or below 3.10, **stop the playbook** and tell the user:

> *"I need Python 3.10 or newer to install the SocPi/Editorial dependencies. Please install it from <https://www.python.org/downloads/> (on Windows, check the 'Add Python to PATH' box during install). Re-run me once it's on your PATH."*

**1c. Node ≥ 18.** Required by EMR and TDM-EMR.

- `node --version`

If missing or below v18, tell the user (but you can still continue with the SocPi install — Node is only needed when they actually run EMR/TDM-EMR). Surface the recommendation:

> *"Node 18+ isn't on your PATH. SocPi will install fine without it, but you'll need Node from <https://nodejs.org/> (LTS) before the EMR or TDM-EMR workspace skills work."*

#### Step 2 — Copy SocPi user skills into `~/.claude/skills/`

Two folders:

| From (this repo) | To |
|---|---|
| `SocPi/if-exclusives-audit/` | `~/.claude/skills/if-exclusives-audit/` |
| `SocPi/if-exclusives-audit-quick/` | `~/.claude/skills/if-exclusives-audit-quick/` |

**2a. Check for existing installs first.**

- POSIX: `[ -d ~/.claude/skills/if-exclusives-audit ]`
- PowerShell: `Test-Path "$env:USERPROFILE\.claude\skills\if-exclusives-audit"`

If a destination exists, **STOP and ask the user** whether to overwrite. The existing folder may contain their real `secrets/gsheets-sa.json` (a Google service-account private key — never re-create, paste, or transmit its contents) and any local edits. Do not delete or `-Force` overwrite without explicit user confirmation.

**2b. Copy commands** (only if Step 2a cleared):

- POSIX (macOS / Linux / Git Bash): `mkdir -p ~/.claude/skills && cp -r SocPi/if-exclusives-audit ~/.claude/skills/ && cp -r SocPi/if-exclusives-audit-quick ~/.claude/skills/`
- PowerShell: `$d = "$env:USERPROFILE\.claude\skills"; New-Item -ItemType Directory -Force -Path $d | Out-Null; Copy-Item -Recurse SocPi\if-exclusives-audit $d; Copy-Item -Recurse SocPi\if-exclusives-audit-quick $d`

**Folder names at the destination must stay exactly** `if-exclusives-audit` and `if-exclusives-audit-quick` — they must match the `name:` field in each `SKILL.md`. Do not rename.

#### Step 3 — Auto-install Python dependencies

Run pip install yourself — do not ask the user to run it. Always use `python -m pip` (more reliable than bare `pip` when multiple Python installs exist on Windows).

**3a. SocPi deps** (run after Step 2 succeeds):

```
python -m pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt
```

(On POSIX with `python3` as the canonical name, use `python3 -m pip ...`.)

**3b. Editorial deps** (run if the user said "install everything" or specifically mentioned Editorial — Editorial is a workspace skill so it isn't installed via Step 2, but its Python deps still need to be on the system):

```
python -m pip install -r Editorial/.claude/skills/editorial-video-researcher/requirements.txt
```

**3c. Permission fallback.** If pip fails with a permissions error (common on locked-down Windows boxes), retry with `--user`:

```
python -m pip install --user -r <path>
```

If `--user` also fails, **show the user the exact pip output and stop** — don't paper over it with another retry.

**3d. EMR / TDM-EMR Node deps.** Both EMR and TDM-EMR have zero Node dependencies (the scrapers use built-in `fetch`). No `npm install` step. Skip.

#### Step 4 — Do NOT install the workspace skills

`EMR/`, `Editorial/`, and `TDM-EMR/` are intentionally not user skills. They are invoked by `cd`-ing into the bundle folder and running `claude`. Do not copy their `.claude/skills/*` contents anywhere — it would break the relative paths inside their `SKILL.md` files.

#### Step 5 — Surface the four remaining manual steps

After Steps 2 and 3 land successfully, tell the user (in your reply, do **not** run these yourself):

1. **Drop a Google service-account key** at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`. There is a `gsheets-sa.json.example` next to it as a template. SA-key creation flow is in `README.md` under "Setting up the Google service account". The same key works for Editorial — drop a copy at `Editorial/.claude/skills/editorial-video-researcher/secrets/gsheets-sa.json` if they plan to use that skill.
2. **Configure MCP connectors** in Claude Code: Google Drive (used by Editorial + SocPi) and SocialPilot (used by SocPi). Details in `README.md` under "MCP connectors". The OAuth flow has to happen in Claude Code's settings panel — you can't drive it.
3. **Install the `anthropic-skills` plugin** in Claude Code (Settings → Plugins). Used by EMR/TDM-EMR for DOCX rendering and PDF reading. Without it those skills stall at the rendering step.
4. **Restart Claude Code** so the new skills are picked up under `/`. Until they restart, `/if-exclusives-audit` will not appear in the slash-command list.

#### Step 6 — If the user wants a workspace skill (EMR / Editorial / TDM-EMR)

Don't run the SocPi install playbook. Just tell them:

```
cd EMR        # or Editorial, or TDM-EMR
claude
```

The skill auto-loads from `<bundle>/.claude/skills/<name>/SKILL.md`. Editorial still needs its Python deps from Step 3b and its SA key from Step 5.1; TDM-EMR additionally needs `Media Kit.pdf` dropped into the workspace root for the Recommendations section.

## Things to never do in this repo

- **Never commit anything from `secrets/`** other than `*.example` and `.gitkeep`. The `.gitignore` already enforces this; do not add a force-include rule for `*.json`.
- **Never reference, paste, or transmit the contents of any `secrets/gsheets-sa.json` file** even when reading it for verification. It is a private key.
- **Never commit `Media Kit.pdf` files** (gitignored — they are licensed product catalogs from the publishers).
- **Never commit run outputs** (anything under `*/output/`, `*/cache/`, `*/runs/`, `*/xml_feeds/*.xml`).
- **Never rewrite `SKILL.md` content** unless the user explicitly asks for that skill's behavior to change. They are battle-tested runbooks; small edits can have large downstream effects.
- **Never push to `main` without an explicit user request** for that specific push. The user reviews each commit themselves.

## Quick map

```
.
├── README.md                      ← long-form docs (humans + agents)
├── CLAUDE.md                      ← this file
├── .gitignore
├── EMR/                           ← workspace skill
├── Editorial/                     ← workspace skill (needs SA key + Python deps)
├── TDM-EMR/                       ← workspace skill (needs Media Kit.pdf for Recommendations)
└── SocPi/
    ├── if-exclusives-audit/       ← user skill — install to ~/.claude/skills/
    └── if-exclusives-audit-quick/ ← user skill — install to ~/.claude/skills/
```
