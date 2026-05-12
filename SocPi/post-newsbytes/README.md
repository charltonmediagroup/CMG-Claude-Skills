# post-newsbytes

Schedule one weekly NewsBytes article to SocialPilot's "Asia-Pacific Broadcasting+" group (4 APB accounts — Facebook, Instagram, LinkedIn, X) with the platform-specific caption tweaks the team uses.

## What it does

For a single user-supplied row of the "Weekly NewsBytes Engagement [CMG]" sheet:

1. Reads the row (column B → schedule time, column C → Drive folder/Doc link, column D → article URL).
2. Follows the column-C link, fetches the Doc body, extracts the **Social media text** + **Key words** + image.
3. Shortens the column-D URL via Bitly.
4. Builds three caption variants (FB/LI = body + "Read more:" + hashtags + `#broadcast #broadcasting`; IG = body + bare URL, no hashtags, image resized 1080×1080; X = ≤200 chars + bare URL + only `#broadcast #broadcasting`).
5. Schedules the post via SocialPilot's `CreatePost` MCP tool, against the four APB accountIds (or four separate calls if `CreatePost` doesn't support per-account variants in one call).
6. Writes a per-row run report under `runs/`.

## Invocation

```
/post-newsbytes <row>
```

E.g. `/post-newsbytes 1595` for the Setplex row in the screenshot. Always requires a row number — the skill never processes more than one row per run.

## Files

- `skills/post-newsbytes/SKILL.md` — the runbook Claude Code follows. Installs to `~/.claude/skills/post-newsbytes/`.
- `run.py` — single CLI entry: `collect | fetch-doc | shorten | report`.
- `lib/` — Python helpers (auth, sheet read, Drive fetch, caption builder, Bitly, image resize, SocialPilot config cache).
- `config.yaml` — platform IDs + cached APB group/account IDs + global hashtags.
- `secrets/api_keys.json` — gitignored. Bitly token, sheet ID, tab name, SA path, timezone.
- `cache/row-<N>.json` — per-row state across CLI steps (regenerated each run).
- `cache/row-<N>.<ext>` and `cache/row-<N>-ig.jpg` — downloaded image + IG-resized variant.
- `runs/post-newsbytes-<N>-<date>.md` — final run report.

## Setup

See [INSTALL.md](INSTALL.md). Installs to two places (bundle code → `~/.claude/post-newsbytes/`, thin SKILL.md → `~/.claude/skills/post-newsbytes/`).

## Authentication

- **Google Sheets + Drive + Docs** — service-account key at `~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json` (reused from `if-exclusives-audit`). The SA must be:
  - **Editor** on the NewsBytes sheet (read access alone is enough today, but Editor avoids friction if we ever write back).
  - **Viewer** on each NewsBytes Drive folder (the column-C target).
  - **Content Manager** on the image staging Shared Drive folder (see INSTALL.md Step 4b — required for SA uploads of the IG-resized JPEG).
- **Bitly** — access token from bitly.com → Profile → API → Generate Access Token. Stored under `bitly_token` in `secrets/api_keys.json`.
- **SocialPilot** — MCP connector configured in Claude Code Settings (already required by `if-exclusives-audit`).

## Why split into four CLI subcommands

`collect` / `fetch-doc` / `shorten` / `report` are read-only or local-only; the only side-effecting step is the SocialPilot post itself, which lives in the SKILL.md (Step 7) so Claude can pause for user approval right before pulling the trigger. Splitting the read steps lets the user re-run any of them in isolation when debugging without re-executing the SocialPilot post.

## Re-runs

The four CLI steps are idempotent — re-running them just refreshes `cache/row-<N>.json`. The MCP `CreatePost` call is **not** idempotent. Re-running a row that's already been posted in this session creates a duplicate. The SKILL.md guards against this — it asks before re-posting.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `secrets error: Missing …/api_keys.json` | First-run setup not complete | Copy `api_keys.json.example` to `api_keys.json` and fill in the placeholders. |
| `Service account key not found at …` | SA key not in the expected path | Check `sa_path` in `api_keys.json` and that `if-exclusives-audit` is installed. |
| `row N column C is not hyperlinked …` | The row's column C is plain text | Check that the article title is hyperlinked to the Drive folder/Doc. |
| `permission denied` from Drive | SA isn't a viewer on the folder | Share the Drive folder with the SA email (read from the SA JSON's `client_email`) as Viewer. |
| `bit.ly returned HTTP 403` | Bad/expired Bitly token | Regenerate at bitly.com → Profile → API. |
| GroupList finds no APB-named group | Group renamed in SocialPilot | Update `default_group` in `secrets/api_keys.json` to match the new name, or rename the group back. |
| `CreatePost` rejects the image | Format/size out of bounds | The skill retries caption-only; manually attach the image at `cache/row-<N>-ig.jpg` (IG) or `cache/row-<N>.<ext>` (others). |
