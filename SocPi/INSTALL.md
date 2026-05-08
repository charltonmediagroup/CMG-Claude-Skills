# Install — SocPi user skills

Single-target install: both folders go into `~/.claude/skills/` so the slash commands `/if-exclusives-audit` and `/if-exclusives-audit-quick` work from any folder. The quick variant has no scripts of its own — it piggybacks on the main skill's `scripts/`, `cache/`, and `secrets/`. **Install both together.**

For architecture, sheet schema, and runtime behavior see [`SocPi/README.md`](README.md).

## Prerequisites

- Python ≥ 3.10 on PATH
- Claude Code with the **SocialPilot** and **Google Drive** MCP connectors configured (Settings → MCP). The SocialPilot account must own the 20 Charlton Media social profiles.
- A Google service-account key with Editor access to the *Commercial SocPi - Links* sheet (file ID `1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`). SA setup walkthrough: [top-level `README.md`](../README.md#setting-up-the-google-service-account-one-time).

## Step 1 — Copy both skill folders

PowerShell:

```powershell
$skillsHome = "$env:USERPROFILE\.claude\skills"
New-Item -ItemType Directory -Force -Path $skillsHome | Out-Null
foreach ($name in @("if-exclusives-audit","if-exclusives-audit-quick")) {
  $dst = Join-Path $skillsHome $name
  if (Test-Path $dst) { Write-Host "$dst exists — investigate before overwriting (may contain your real SA key)"; exit 1 }
  Copy-Item -Recurse "SocPi\$name" $skillsHome
}
```

POSIX (bash):

```bash
mkdir -p ~/.claude/skills
for n in if-exclusives-audit if-exclusives-audit-quick; do
  dst="$HOME/.claude/skills/$n"
  [ -d "$dst" ] && { echo "$dst exists — investigate before overwriting (may contain your real SA key)"; exit 1; }
  cp -r "SocPi/$n" "$HOME/.claude/skills/"
done
```

The destination folder names must stay exactly `if-exclusives-audit` and `if-exclusives-audit-quick` — they match the `name:` field in each `SKILL.md` and are how Claude Code resolves the slash commands.

## Step 2 — Install Python deps

```
python -m pip install -r ~/.claude/skills/if-exclusives-audit/requirements.txt
```

(`requirements.txt`: gspread, google-auth, rapidfuzz, requests, PyYAML.) If pip fails with permissions, retry with `--user`.

## Step 3 — Drop the SA key

Copy the example template, then replace its contents with the real key:

```
cp ~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json.example \
   ~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json
```

Then overwrite `gsheets-sa.json` with the JSON downloaded from Google Cloud Console → IAM & Admin → Service Accounts → Keys → Add key → JSON. The file is gitignored — it never leaves your machine.

Share the *Commercial SocPi - Links* sheet (`1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`) with the SA's `client_email` as **Editor**.

## Step 4 — Configure MCP connectors

In Claude Code's settings panel:

| Connector | Tools the skills call | Auth |
|---|---|---|
| **SocialPilot** | `DeliveredPosts`, `QueuedPosts`, `GroupList`, `AccountList`, `UserInfo` | API token from the SocialPilot account that owns the 20 publication profiles. |
| **Google Drive** | `download_file_content` | OAuth-authenticated Google account with read access to the sheet. |

The skills address tools by suffix, so the per-machine MCP server ID prefix doesn't have to match the original install.

## Step 5 — Restart Claude Code

The slash commands `/if-exclusives-audit` and `/if-exclusives-audit-quick` only show up after restart.

## Smoke test

From any folder:

```
/if-exclusives-audit-quick
```

The quick variant skips RSS scraping and audits whatever URLs are already in column A of the *IF & Exclusives* tab — fastest way to confirm the SA key works, MCP connectors respond, and the script can write back to the sheet. If column A is empty, run the full `/if-exclusives-audit` instead (it populates column A from the publication RSS feeds first).

## Troubleshooting

- **`FileNotFoundError: gsheets-sa.json`** — Step 3 didn't land. Confirm with `ls ~/.claude/skills/if-exclusives-audit/secrets/`.
- **`gspread.exceptions.APIError: 403 PERMISSION_DENIED`** — sheet wasn't shared with the SA's `client_email`. Open the JSON, copy `client_email`, share the sheet as Editor.
- **MCP tool not found (`__DeliveredPosts` etc.)** — SocialPilot MCP not configured, or its server ID changed. Re-add it under Settings → MCP and confirm the tool list with `/help`.
- **`/if-exclusives-audit-quick` runs but reports `column A is empty`** — expected on a fresh sheet. Run the full `/if-exclusives-audit` once to populate column A from feeds.
