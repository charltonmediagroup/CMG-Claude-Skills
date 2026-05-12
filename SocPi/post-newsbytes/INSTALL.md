# Install — post-newsbytes

Two-target install: bundle code to `~/.claude/post-newsbytes/`, thin SKILL.md to `~/.claude/skills/post-newsbytes/`.

## Prerequisites

- Python ≥ 3.10 (the SocPi skills already require this).
- The SocPi service-account key already in place at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json` (this bundle reuses it; install `if-exclusives-audit` first if you haven't).
- The "Weekly NewsBytes Engagement [CMG]" Google Sheet shared with the SA email as **Editor**.
- Each NewsBytes Drive folder shared with the SA email as **Viewer**.
- A Bitly access token (free tier — bitly.com → Profile → API → Generate Access Token).
- The SocialPilot MCP connector configured in Claude Code Settings (already required by `if-exclusives-audit`).

## Step 1 — Copy the bundle

PowerShell:

```powershell
$src = "$pwd\SocPi\post-newsbytes"
$dst = "$env:USERPROFILE\.claude\post-newsbytes"
if (Test-Path $dst) { Write-Host "Bundle already exists at $dst — investigate before overwriting"; exit 1 }
Copy-Item -Recurse $src $dst
```

POSIX:

```bash
src="SocPi/post-newsbytes"
dst="$HOME/.claude/post-newsbytes"
[ -d "$dst" ] && { echo "$dst exists — investigate before overwriting"; exit 1; }
cp -r "$src" "$dst"
```

## Step 2 — Copy the SKILL.md folder

PowerShell:

```powershell
$bundleSkills = "$env:USERPROFILE\.claude\post-newsbytes\skills"
$skillsHome = "$env:USERPROFILE\.claude\skills"
New-Item -ItemType Directory -Force -Path $skillsHome | Out-Null
$dst = "$skillsHome\post-newsbytes"
if (Test-Path $dst) { Write-Host "$dst already exists — investigate before overwriting"; exit 1 }
Copy-Item -Recurse "$bundleSkills\post-newsbytes" $dst
```

POSIX:

```bash
mkdir -p ~/.claude/skills
[ -d ~/.claude/skills/post-newsbytes ] && { echo "~/.claude/skills/post-newsbytes exists — investigate before overwriting"; exit 1; }
cp -r ~/.claude/post-newsbytes/skills/post-newsbytes ~/.claude/skills/
```

## Step 3 — Install Python dependencies

```
python -m pip install -r ~/.claude/post-newsbytes/requirements.txt
```

If pip fails with permissions, retry with `--user`.

## Step 4 — Populate secrets

```
cp ~/.claude/post-newsbytes/secrets/api_keys.json.example ~/.claude/post-newsbytes/secrets/api_keys.json
```

Open `api_keys.json` and fill in:

| Field | Where to get it |
|---|---|
| `bitly_token` | bitly.com → Profile → API → Generate Access Token |
| `bitly_group_guid` | Optional. Leave `""` to let Bitly pick the default group. Find it via `GET https://api-ssl.bitly.com/v4/groups` if you want to pin it. |
| `sheet_id` | The "Weekly NewsBytes Engagement [CMG]" file ID — the long string in the sheet URL between `/d/` and `/edit`. |
| `tab` | The exact tab name where article rows live. |
| `sa_path` | Default reuses the SocPi key at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json`. |
| `image_staging_folder_id` | **Required.** Folder ID inside a Google Shared Drive where the skill uploads IG-resized images. See Step 4b. |
| `timezone` | Default `Asia/Singapore`. Used to interpret column-B times like "May 11, 2026 (3PM)". |
| `default_group` | Default `Asia-Pacific Broadcasting+`. Rename only if the SocialPilot group is renamed. |

## Step 4b — Create the image staging Shared Drive

Service accounts have **zero personal-Drive storage quota**, so they can't upload to a regular Drive folder owned by a real user. They CAN upload to Google **Shared Drives**, where storage is billed to the Workspace.

The skill resizes each row's image to 1080×1080 (Instagram-square format) and needs to host that resized copy somewhere SocialPilot can fetch via a public URL. A dedicated staging folder in a Shared Drive is the cleanest answer.

**One-time setup:**

1. In Google Drive, click **New → Shared Drive**. Name it something like *"CMG SocPi image staging"*. (Requires Google Workspace + Shared Drives enabled by your admin.)
2. Inside the new Shared Drive, create a folder named `post-newsbytes-images/`.
3. Open that folder in Drive and copy the folder ID from the URL (the long string after `/folders/`).
4. Right-click the folder → Share → add the SocPi SA email (`client_email` field from the SocPi SA JSON) as **Content Manager**. *Editor isn't enough — Content Manager is required for SA uploads on a Shared Drive.*
5. Paste the folder ID into `api_keys.json` as `image_staging_folder_id`.

If your team can't enable Shared Drives, the IG-resize feature will fall back to using the row's original image (and IG may auto-crop or reject .webp). The skill warns and continues; everything else still works.

## Step 5 — Share the sheet + Drive folders with the SA

Read the SA email from the SA JSON's `client_email` field — it's something like `openclaw@cmg-agent.iam.gserviceaccount.com`. Share:

- The "Weekly NewsBytes Engagement [CMG]" sheet → **Editor**.
- Each NewsBytes Drive folder (or the parent that contains them all) → **Viewer**.

The skill will refuse to post a row whose Drive folder isn't readable.

## Step 6 — Smoke test

Pick a known row that has a Drive folder + image already populated:

```
python ~/.claude/post-newsbytes/run.py collect   --row 1595
python ~/.claude/post-newsbytes/run.py fetch-doc --row 1595
python ~/.claude/post-newsbytes/run.py shorten   --row 1595
```

Each should print a clear summary and write/update `~/.claude/post-newsbytes/cache/row-1595.json`.

If `collect` fails with `row N column C is not hyperlinked`, check that column C of that row is a clickable link (not just plain text). Some legacy rows may need to be re-linked manually.

## Step 7 — Restart Claude Code

The slash command appears after restart:

- `/post-newsbytes <row>`

## First real run

Per the SKILL.md, the first run will additionally:

1. Resolve the APB SocialPilot group via `GroupList` + `AccountList` MCP tools and cache the four accountIds in `~/.claude/post-newsbytes/config.yaml`.
2. Probe the `CreatePost` MCP schema (the audit skills only call read-side MCP tools, so the write-side schema is unknown until first contact). The discovered shape gets recorded in `lib/socialpilot.py` for future reference.

Plan to do the first run while you have a few minutes to confirm the schema and APB group resolution.
