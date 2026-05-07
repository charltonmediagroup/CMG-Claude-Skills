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

**1. Confirm the cloned repo is at the user's working directory.** If `pwd` / `Get-Location` is not the repo root (the folder containing this `CLAUDE.md`), `cd` there first or ask the user where they cloned it.

**2. Copy the user skills into `~/.claude/skills/`.** Exactly two folders:

| From (this repo) | To |
|---|---|
| `SocPi/if-exclusives-audit/` | `~/.claude/skills/if-exclusives-audit/` |
| `SocPi/if-exclusives-audit-quick/` | `~/.claude/skills/if-exclusives-audit-quick/` |

Cross-platform commands:

- POSIX (macOS / Linux / Git Bash): `mkdir -p ~/.claude/skills && cp -r SocPi/if-exclusives-audit ~/.claude/skills/ && cp -r SocPi/if-exclusives-audit-quick ~/.claude/skills/`
- PowerShell: `$d = "$env:USERPROFILE\.claude\skills"; New-Item -ItemType Directory -Force -Path $d | Out-Null; Copy-Item -Recurse -Force SocPi\if-exclusives-audit $d; Copy-Item -Recurse -Force SocPi\if-exclusives-audit-quick $d`

**Folder names at the destination must stay exactly** `if-exclusives-audit` and `if-exclusives-audit-quick` — they must match the `name:` field in each skill's `SKILL.md`. Do not rename.

**3. Handle existing installs carefully.** Before copying, check whether either destination already exists:

- POSIX: `[ -d ~/.claude/skills/if-exclusives-audit ]`
- PowerShell: `Test-Path "$env:USERPROFILE\.claude\skills\if-exclusives-audit"`

If a destination exists, **STOP and ask the user** whether to overwrite. The existing folder may contain their `secrets/gsheets-sa.json` (a real Google service-account key — never re-create or share its contents) and any local edits. Do not delete or `-Force` overwrite without explicit user confirmation.

**4. Do NOT install the workspace skills.** `EMR/`, `Editorial/`, and `TDM-EMR/` are intentionally not user skills. They are invoked by `cd`-ing into the bundle folder and running `claude`. Do not copy their `.claude/skills/*` contents anywhere — it would break the relative paths inside their `SKILL.md` files.

**5. Tell the user the next four manual steps.** Do not do these for them automatically — they involve credentials, third-party setup, and a Claude Code restart. Surface them in your reply:

1. **Drop a Google service-account key** at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`. There is a `gsheets-sa.json.example` next to it as a template. SA-key creation flow is in `README.md` under "Setting up the Google service account". The same key works for the Editorial workspace skill if they plan to use it (drop a copy at `Editorial/.claude/skills/editorial-video-researcher/secrets/gsheets-sa.json`).
2. **Install Python dependencies**: `pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt`.
3. **Configure MCP connectors** in Claude Code: Google Drive (used by Editorial + SocPi) and SocialPilot (used by SocPi). Details in `README.md` under "MCP connectors".
4. **Restart Claude Code** so the new skills are picked up under `/`. Until they restart, `/if-exclusives-audit` will not appear in the slash-command list.

**6. If the user actually wants a workspace skill (EMR / Editorial / TDM-EMR)**, do not run the install playbook. Just tell them to `cd` into that bundle and run `claude` there. The skill auto-loads from `<bundle>/.claude/skills/<name>/SKILL.md`.

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
