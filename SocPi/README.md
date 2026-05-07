# SocPi — IF & Exclusives distribution audit

Two related Claude Code skills for auditing IF/EXCLUSIVE article distribution across the 20 Charlton Media publications and their Facebook, Instagram, LinkedIn, and X accounts. Reads the canonical *Commercial SocPi - Links* sheet (tab `IF & Exclusives`), pulls delivered + queued posts from SocialPilot via MCP, and writes per-platform permalinks (or `SCHEDULED` markers) back to columns D-H.

## Skills

| Skill | Purpose | When to use |
|---|---|---|
| [`if-exclusives-audit/`](if-exclusives-audit/README.md) | Full audit pipeline. Scrapes RSS feeds → populates column A → fetches SocialPilot → matches → writes back to columns D-H. | First-time audit, weekly refresh, or whenever you want column A regenerated from feeds. |
| [`if-exclusives-audit-quick/`](if-exclusives-audit-quick/README.md) | Skips RSS scraping. Reads column A as-is, otherwise identical. | Re-audit on the same URL set, or when feeds are flaky. **Depends on `if-exclusives-audit/`** for scripts and secrets. |

## Packaging — these are user skills

Unlike the EMR/Editorial/TDM-EMR workspaces in this repo, the two SocPi skills are intended to be **installed into your Claude Code user-skills directory** so the slash commands work from any folder on disk.

The easiest install path is to ask Claude Code itself:

> *"Install the skills from this repo."*

It will read [the Installation section in the root `README.md`](../README.md#installation) (and [`CLAUDE.md`](../CLAUDE.md)) and run the right copy commands for your OS — **including `python -m pip install -r requirements.txt`** — then surface the remaining manual steps (SA key, MCP connectors, `anthropic-skills` plugin, Claude Code restart). Manual install is also fine:

```bash
# Windows (in bash / Git Bash)
cp -r if-exclusives-audit       "$USERPROFILE/.claude/skills/"
cp -r if-exclusives-audit-quick "$USERPROFILE/.claude/skills/"

# macOS / Linux
cp -r if-exclusives-audit       ~/.claude/skills/
cp -r if-exclusives-audit-quick ~/.claude/skills/
```

The folder names **must** be `if-exclusives-audit` and `if-exclusives-audit-quick` — they match the `name` field in each `SKILL.md` and are how Claude Code resolves the slash commands.

Install **both**: the quick variant calls into the main skill's `scripts/` and `secrets/` folders. Installing only the quick skill will fail at runtime when it tries to `cd` into the main skill's directory.

## Requirements

- **Python 3.10+** with `pip install -r if-exclusives-audit/requirements.txt` (gspread, google-auth, rapidfuzz, requests, PyYAML).
- **Claude Code** with two MCP connectors configured:
  - **SocialPilot** — used for `DeliveredPosts`, `QueuedPosts`, `GroupList`, `AccountList`, `UserInfo`. Must be authenticated as the account that owns the 20 Charlton Media social profiles.
  - **Google Drive** — used for `download_file_content` (sheet CSV export).
- A **Google service-account key** with Editor access to the *Commercial SocPi - Links* sheet (`1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`). See the top-level [`README.md`](../README.md#setting-up-the-google-service-account-one-time) for SA setup.

## Setup

1. Copy both folders into `~/.claude/skills/` (snippet above).
2. Install Python deps:
   ```bash
   pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt
   ```
3. Configure the SocialPilot and Google Drive MCP connectors in Claude Code (Settings → MCP).
4. Create your SA key (see top-level README) and share the *Commercial SocPi - Links* sheet with the SA email as **Editor**. Drop the JSON at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`. Use `gsheets-sa.json.example` as a template.
5. From any folder, in Claude Code:
   ```
   /if-exclusives-audit
   ```

## Source of truth (strict)

- **Spreadsheet**: file ID `1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk` (*Commercial SocPi - Links*).
- **Tab**: `IF & Exclusives` only.
- **Column A** = article URL (every row is treated as IF or EXCLUSIVE; URL paths are unreliable, so don't filter on them).

## Output (sheet columns D-H)

| Col | Header | Cell content |
|---|---|---|
| D | Facebook URL | `=HYPERLINK("<permalink>","<post headline>")`, or `SCHEDULED 2026-05-02 10:00`, or empty |
| E | Instagram URL | same |
| F | LinkedIn URL | same |
| G | X URL | same |
| H | Status | one of `COMPLETE`, `PARTIAL`, `SCHEDULED`, `MISSING`, `DUPLICATE ISSUE` |

Status hierarchy: `DUPLICATE ISSUE > COMPLETE > PARTIAL > SCHEDULED > MISSING`.

## What's gitignored

The top-level `.gitignore` covers SocPi's per-run scratch:

- `if-exclusives-audit/cache/{sheet.csv,articles.json,posts.json,matches.json,manual_overrides.json,shortlinks.json,account_map.json}`
- `if-exclusives-audit/cache/responses/<run-id>/` (per-run MCP dumps)
- `if-exclusives-audit/runs/audit-*.{md,csv}` (per-run reports)
- `if-exclusives-audit/secrets/*.json` (real SA keys; the `.example` is committed)

`shortlinks.json` and `account_map.json` are seeded on first run and rebuilt as the bundle encounters new short-links / accounts. They're gitignored to avoid leaking team-internal SocialPilot account IDs.

## Per-skill READMEs

Both skills have their own README with detailed runbooks and troubleshooting:

- [`if-exclusives-audit/README.md`](if-exclusives-audit/README.md) — full setup + runbook
- [`if-exclusives-audit-quick/README.md`](if-exclusives-audit-quick/README.md) — quick variant, dependency notes
