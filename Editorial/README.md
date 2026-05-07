# Editorial — Discussion Topic Researcher

Workspace for `/editorial-video-researcher` — pulls each Charlton publication's top-read XML feed, drafts a one-paragraph AI summary plus five C-suite interview questions per article, and appends the result directly to the `[2026] Discussion Topic` tab of the *Copy of 2025-2026 Asian Business Media* Google Sheet.

## What's here

```
Editorial/
├── README.md                                    ← this file
├── xml_feeds/                                   ← runtime feed dumps (gitignored)
└── .claude/skills/editorial-video-researcher/
    ├── SKILL.md                                 ← runbook Claude Code follows
    ├── config.yaml                              ← 11 publications + feed URLs + dedupe rules
    ├── requirements.txt                         ← Python deps (gspread, google-auth, PyYAML)
    ├── scripts/
    │   ├── fetch_feed.py                        ← top-read feed → article URLs
    │   ├── fetch_article.py                     ← URL → title + body text
    │   ├── sheet_existing_urls.py               ← dedupe column D
    │   ├── sheet_next_empty_row.py              ← find the next free row in column A
    │   └── sheet_write_row.py                   ← gspread row append
    └── secrets/
        ├── gsheets-sa.json                      ← (gitignored) drop your SA key here
        └── gsheets-sa.json.example              ← committed template
```

## Requirements

- **Python 3.10+** with deps from [`requirements.txt`](.claude/skills/editorial-video-researcher/requirements.txt) (`gspread`, `google-auth`, `PyYAML`). Installed automatically by the agent install playbook in the top-level [`README.md`](../README.md#installation); manual install is `python -m pip install -r .claude/skills/editorial-video-researcher/requirements.txt`.
- **Claude Code** opened with the `Editorial/` folder as the working directory.
- **Google Drive MCP connector** in Claude Code (used to read the source sheet).
- A **Google service-account key** with Editor access to the *Copy of 2025-2026 Asian Business Media* sheet (`1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU`). See the top-level [`README.md`](../README.md#setting-up-the-google-service-account-one-time) for SA setup.

## Setup

1. Create your SA JSON key (see top-level README) and share the sheet with the SA email as **Editor**.
2. Drop the JSON file at `Editorial/.claude/skills/editorial-video-researcher/secrets/gsheets-sa.json`. The repo's `.gitignore` keeps it out of git.
3. From this folder:
   ```bash
   cd "C:\Users\USER\Desktop\CMG Claude Skills\Editorial"
   claude
   ```

## Usage

Inside Claude Code:

```
/editorial-video-researcher                # default 3 articles per pub, all 11 pubs
/editorial-video-researcher SBR HKB        # 3 each from SBR + HKB only
/editorial-video-researcher SBR=2 HKB=1    # per-pub override
```

The orchestrator follows `SKILL.md` exactly:

1. Loads `config.yaml` to find each publication's top-read XML feed URL.
2. Fetches the feed for each requested pub, parses article URLs, drops anything matching the excluded path segments (`/event-news/`, `/commentary/`, `/co-written-partner/`, `/videos/`).
3. Reads column D of the `[2026] Discussion Topic` tab and dedupes — already-processed URLs are skipped.
4. For each new article: fetches the page, drafts a magazine-quality summary + five C-suite interview questions, and appends a row to the next empty cell in column A.

## Publications

11 publications wired into `config.yaml`:

| Abbrev | Full name |
|---|---|
| SBR | Singapore Business Review |
| HKB | Hong Kong Business |
| ABF | Asian Banking & Finance |
| IA | Insurance Asia |
| RA | Retail Asia |
| HCA | Healthcare Asia |
| AP | Asian Power |
| GovMedia | GovMedia |
| MA | Manufacturing Asia |
| AT | Asian Telecom |
| REA | Real Estate Asia |

Add or rename publications by editing `config.yaml`; the skill reads it on each run.

## Source of truth

- **Spreadsheet**: file ID `1QD8X7lphuy0ryxqhHKMxYYVARm2IB9IlRheBlt21xdU` (*Copy of 2025-2026 Asian Business Media*).
- **Tab**: `[2026] Discussion Topic` only.
- **Dedupe column**: D (article URL).
- **Insert column**: A (next empty row on the tab).

## Troubleshooting

| Problem | Fix |
|---|---|
| `FileNotFoundError: secrets/gsheets-sa.json` | Drop your SA JSON key into the `secrets/` folder (use `gsheets-sa.json.example` as a template). |
| Sheet write returns 403 | The SA email isn't shared on the sheet, or doesn't have Editor permission. |
| Feed fetch times out | The publication's top-read feed is flaky. Re-run; the skill is idempotent (already-written URLs are skipped). |
| No new rows added | Likely all top-read URLs are already in column D — try a different pub or wait for the feed to roll over. |
