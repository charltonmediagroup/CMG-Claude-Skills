# Install — competitors-and-leads bundle

Two-target install: the bundle code goes to `~/.claude/competitors-and-leads/`,
and 5 thin SKILL.md folders go to `~/.claude/skills/`.

## Prerequisites

- Python ≥ 3.10 (the SocPi skills already require this)
- The SocPi service-account key in place at
  `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`
  (this bundle reuses it; if you haven't installed SocPi yet, do that first
  per the repo's `CLAUDE.md`)
- The sheet `Existing Clients (2021 to 2025)` shared with the SA's email as Editor
- API keys for **SerpAPI**, **Tavily**, **Apify**, **Hunter.io**

## Step 1 — Copy the bundle

PowerShell:

```powershell
$src = "$pwd\Sales\competitors-and-leads"
$dst = "$env:USERPROFILE\.claude\competitors-and-leads"
if (Test-Path $dst) { Write-Host "Bundle already exists at $dst — investigate before overwriting"; exit 1 }
Copy-Item -Recurse $src $dst
```

POSIX (bash):

```bash
src="Sales/competitors-and-leads"
dst="$HOME/.claude/competitors-and-leads"
[ -d "$dst" ] && { echo "$dst exists — investigate before overwriting"; exit 1; }
cp -r "$src" "$dst"
```

## Step 2 — Copy the 5 SKILL.md folders

PowerShell:

```powershell
$bundleSkills = "$env:USERPROFILE\.claude\competitors-and-leads\skills"
$skillsHome = "$env:USERPROFILE\.claude\skills"
foreach ($name in @("sales-find-competitors","sales-find-pocs","sales-research-competitor","sales-draft-emails","sales-pipeline-all")) {
  Copy-Item -Recurse "$bundleSkills\$name" "$skillsHome\$name"
}
```

POSIX:

```bash
mkdir -p ~/.claude/skills
for n in sales-find-competitors sales-find-pocs sales-research-competitor sales-draft-emails sales-pipeline-all; do
  cp -r ~/.claude/competitors-and-leads/skills/$n ~/.claude/skills/
done
```

## Step 3 — Install Python deps

```
python -m pip install -r ~/.claude/competitors-and-leads/requirements.txt
```

If pip fails with permissions, retry with `--user`.

## Step 4 — Populate secrets

Copy the example file:

```
cp ~/.claude/competitors-and-leads/secrets/api_keys.json.example ~/.claude/competitors-and-leads/secrets/api_keys.json
```

Open `api_keys.json` and fill in:

| Field | Where to get it |
|---|---|
| `serpapi` | n8n → Credentials → "Marketing" credential, copy the API key |
| `tavily` | n8n workflow JSON, in the body of any `p2-tavily-*` HTTP node |
| `apify` | n8n workflow JSON, in the URL of any `p2-apify*` HTTP node (after `?token=`) |
| `hunter` | n8n workflow JSON, in the URL of the `p2-hunter` HTTP node (after `&api_key=`) |
| `sheet_id` | Default is `17UoMrLJUC_rwuMhWEqR2F9xejKXCjc5sSbIjatga65w`. Change if you target a different sheet. |
| `sa_path` | Default reuses the SocPi key at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`. Change if you have a separate one. |

## Step 5 — Smoke test

```
python ~/.claude/competitors-and-leads/run.py phase1-collect --dry-run
python ~/.claude/competitors-and-leads/run.py phase2-collect --dry-run
python ~/.claude/competitors-and-leads/run.py phase3-collect --dry-run
python ~/.claude/competitors-and-leads/run.py phase4-collect --dry-run
```

Each should print a candidate count and exit cleanly. None of these touch
external APIs in `--dry-run` mode.

## Step 6 — Restart Claude Code

The new slash commands `/sales-find-competitors`, `/sales-find-pocs`,
`/sales-research-competitor`, `/sales-draft-emails`, and
`/sales-pipeline-all` show up after restart.

## Concurrency note

If you also run the n8n `Sales - Competitors and Leads` workflow against
the same sheet, **pause it during a skill run**. Both pipelines write to
the same tabs. The skill's skip-set check prevents duplicate rows but a
race could still cause a competitor to be processed twice.
