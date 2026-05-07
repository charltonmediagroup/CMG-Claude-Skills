# IF & EXCLUSIVE Distribution Audit — Skill Bundle

End-to-end audit of IF/EXCLUSIVE article distribution across 20 Charlton Media publications and their Facebook, Instagram, LinkedIn, and X accounts. Reads the canonical Google Sheet, pulls delivered + queued posts from SocialPilot, and writes per-platform permalinks (or `SCHEDULED` markers) back to columns D-H of the sheet.

Invoke with `/if-exclusives-audit` inside Claude Code.

---

## Setup on a new machine

### 1. Install the skill

Copy this entire folder to the user-skills directory:

```
Windows:  C:\Users\<you>\.claude\skills\if-exclusives-audit\
macOS/Linux: ~/.claude/skills/if-exclusives-audit/
```

The folder name **must** be `if-exclusives-audit` (matches the skill name in `SKILL.md`).

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

Python 3.10+ recommended (script uses `dict[int, ...]` annotations).

### 3. Install Claude Code MCP connectors

Two MCP servers must be configured in Claude Code on the new machine:

| Connector | Purpose | Tools used |
|---|---|---|
| **SocialPilot** | Post data | `DeliveredPosts`, `QueuedPosts`, `GroupList`, `AccountList`, `UserInfo` |
| **Google Drive** | Sheet CSV export | `download_file_content` |

Use the same SocialPilot account that owns the 20 Charlton Media social profiles. The Drive connector needs read access to the source Google Sheet.

The MCP server IDs (e.g. `mcp__ae062ea4-…`) will differ per-machine — that's fine, the skill addresses tools by suffix (`__DeliveredPosts`, etc.).

### 4. Service-account credentials

`secrets/gsheets-sa.json` is the Google service-account key used to write back to the sheet via `gspread`.

- Email: `openclaw@cmg-agent.iam.gserviceaccount.com`
- Already shared as **Editor** on the source sheet (`1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk`).

> ⚠️ **Do not commit this file or share the bundle publicly with the SA file inside.** The private key in `gsheets-sa.json` lets anyone with it write to the sheet. If you need to share the skill with someone outside the team, delete the file before sharing and let them generate their own SA key (then share the sheet with their SA email).

### 5. Verify

```bash
cd ~/.claude/skills/if-exclusives-audit
python scripts/write_to_sheet.py cache/matches.json \
    --sa secrets/gsheets-sa.json \
    --sheet-id 1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk \
    --tab "IF & Exclusives" --dry-run
```

If it prints `Articles in sheet: 21 ... Mode: DRY-RUN (no writes)` you're set.

---

## Running

Inside Claude Code:

```
# All 19 publications:
/if-exclusives-audit

# Specific pubs (acronyms are case-insensitive):
/if-exclusives-audit SBR HKB
/if-exclusives-audit sbr,hkb,abf
/if-exclusives-audit QSR             # alias → all three QSR Media variants
/if-exclusives-audit SBR QSR ESG     # mix bare acronyms and aliases freely
```

Acronyms and aliases are defined in `config.yaml` under `publications:` and `publication_aliases:`. Run `python scripts/collect_urls.py --list-pubs` to see the full set. The 19 supported acronyms are:

`SBR`, `ABF`, `HCA`, `HKB`, `RA`, `REA`, `ABR`, `IA`, `AP`, `QSR-A`, `QSR-AU`, `QSR-UK`, `MA`, `AT`, `GovMedia`, `ESG`, `MR`, `DA`, `FA`. Aliases: `all` and `QSR`.

**Important — every run wipes A2:H1000 of the sheet.** Filtered runs only refresh the selected pubs' rows; other pubs' historical data in the sheet is gone after the run. Re-run with no filter (or with their acronyms) to repopulate.

The orchestrator follows `SKILL.md` exactly:

1. Generates a per-run ID and run-dir
2. **Resolves the publication selector** (filter → list of allowed hostnames)
3. Wipes A2:H1000 and writes the deduped URLs for selected pubs only
4. Downloads the sheet → `cache/articles.json`
5. Resolves account map (cached)
6. Pulls **DeliveredPosts** + **QueuedPosts** for every article in `articles.json` — **in parallel**
7. Aggregates into `cache/posts.json`
8. URL-first matches articles to posts
9. Writes the markdown + CSV report to `runs/audit-<date>.{md,csv}`
10. **Auto-commits** results to columns D-H of the sheet

Default is auto-commit. If you want a preview first, run the last script manually with `--dry-run`.

---

## Folder layout

```
if-exclusives-audit/
├── SKILL.md                  ← skill definition + orchestrator instructions
├── README.md                 ← this file
├── requirements.txt          ← Python deps
├── config.yaml               ← groups map, platform IDs, thresholds
├── .gitignore                ← keeps secrets + scratch out of git
├── scripts/
│   ├── fetch_articles.py     ← CSV → articles.json
│   ├── save_mcp_response.py  ← stdin JSON → file helper
│   ├── aggregate_posts.py    ← per-run-dir → posts.json
│   ├── match.py              ← articles + posts → matches.json
│   ├── report.py             ← matches → markdown + CSV
│   └── write_to_sheet.py     ← matches → sheet (auto-commit)
├── cache/
│   ├── account_map.json      ← seeded; loginId map (FB/IG/LI/X per pub)
│   ├── shortlinks.json       ← seeded; resolved short-link cache
│   └── responses/            ← per-run-id MCP dumps (regenerated each run)
├── runs/                     ← audit-YYYY-MM-DD.{md,csv}
└── secrets/
    └── gsheets-sa.json       ← Google service-account key (gitignored)
```

---

## Source of truth

- **Spreadsheet**: file ID `1DsjxLnlZDZmZMPuvVJaKLZ_rWgZML-AxuQ6zRSS1TXk` ("Commercial SocPi - Links")
- **Tab**: `IF & Exclusives`
- **Column A** = article URL — every row is treated as IF or EXCLUSIVE.

## Output (sheet columns D-H)

| Col | Header | Cell content |
|---|---|---|
| D | Facebook URL | permalink, or `SCHEDULED 2026-05-02 10:00`, or empty |
| E | Instagram URL | same |
| F | LinkedIn URL | same |
| G | X URL | same |
| H | Status | one of: `COMPLETE` `PARTIAL` `SCHEDULED` `MISSING` `DUPLICATE ISSUE` |

Status hierarchy: `DUPLICATE ISSUE > COMPLETE > PARTIAL > SCHEDULED > MISSING`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: gspread` | `pip install -r requirements.txt` |
| `FileNotFoundError: secrets/gsheets-sa.json` | Add the SA key file (or generate a new one and share the sheet with the SA email) |
| `Empty cache/responses/<run-id>/` | An MCP call failed silently — check the SocialPilot connector is connected in Claude Code |
| Aggregator says `posted: 0, scheduled: 0` | Filename convention broken — must be `<pub-host>__<platform>__<delivered\|queued>.json` |
| Sheet write returns 403 | Service-account email isn't shared on the sheet (give it Editor access) |
