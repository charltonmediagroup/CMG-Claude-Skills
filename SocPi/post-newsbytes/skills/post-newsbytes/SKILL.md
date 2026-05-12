---
name: post-newsbytes
description: Post a single Weekly NewsBytes article to SocialPilot's "Asia-Pacific Broadcasting+" group (4 APB accounts — Facebook, Instagram, LinkedIn, X) with the platform-specific caption tweaks the team uses. Reads the user-supplied row from the "Weekly NewsBytes Engagement [CMG]" Google Sheet, follows the column-C hyperlink to the row's Google Drive folder/Doc, extracts the Social Media text + keywords + image, shortens the column-D article URL via Bitly, builds the per-platform caption variants (FB/LI keep "Read more:" + all hashtags + #broadcast #broadcasting; IG drops "Read more:" + all hashtags, image resized 1080×1080; X trims body to ≤200 chars + drops "Read more:" + keeps only #broadcast #broadcasting), then schedules the post via the SocialPilot MCP using the date in column B (falls back to draft if the date is past or unparseable). Use when the user invokes /post-newsbytes <row>, says "post the newsbytes for row 1595", "schedule the SocPi post for the Setplex article", or otherwise asks to push a row from the NewsBytes sheet to SocialPilot. ALWAYS requires a row number — ask the user if they didn't supply one.
---

# /post-newsbytes — Schedule one NewsBytes article to SocialPilot

End-to-end posting of one row from the "Weekly NewsBytes Engagement [CMG]" sheet to SocialPilot's APB group. The skill handles the full manual flow: open the sheet → follow the Drive link → copy caption → shorten URL → build per-platform variants → schedule via SocialPilot.

## Where the code lives

`~/.claude/post-newsbytes/` — single canonical bundle. The `run.py` CLI does the read-only data work (sheet read, Drive fetch, Bitly shorten, image resize); the SocialPilot MCP calls happen in your conversation.

## Source of truth (strict)

- **Spreadsheet**: file ID + tab name come from `~/.claude/post-newsbytes/secrets/api_keys.json` (`sheet_id`, `tab`).
- **Column B** = scheduled date/time in the form `May 11, 2026 (3PM)`. Timezone is `Asia/Singapore` unless overridden in `secrets`.
- **Column C** = article title; the cell is hyperlinked to a Google Drive folder/Doc.
- **Column D** = canonical article URL (the one to shorten).
- **One row per run.** No sheet-wide scan. The user must supply a row number.
- **Image staging Shared Drive folder**: `image_staging_folder_id` in `secrets/api_keys.json`. Must be a Google Shared Drive (not personal Drive — service accounts have zero personal-Drive storage quota) with the SocPi SA as Content Manager. Used to host the IG-resized image so SocialPilot can fetch it via a public URL.

## Per-platform caption rules (the team's actual workflow)

| Platform | Body | URL | Hashtags | Media |
|---|---|---|---|---|
| Facebook | full Social Media text from the Doc | `Read more: <bitly>` | `#kw1 #kw2 ... #broadcast #broadcasting` | image as-is |
| LinkedIn | same as Facebook | same | same | same |
| Instagram | same body | bare `<bitly>` (no "Read more:" prefix) | none | image resized to 1080×1080 padded |
| X | body trimmed so total post ≤200 chars; body, URL, hashtags separated by blank lines | bare `<bitly>` on its own line (no "Read more:" prefix) | only `#broadcast #broadcasting` on a separate line | image as-is |

## Execution flow (the orchestrator follows this exactly)

### Step 0 — Parse invocation

Read `$ARGUMENTS`. Expect a single integer (the row number). If absent or non-numeric, **stop and ask the user** which row to post. Do not guess.

### Step 1 — Read the row

```
python ~/.claude/post-newsbytes/run.py collect --row <N>
```

This opens the configured sheet/tab via the SocPi service-account key, reads row N, parses column B with `python-dateutil`, and writes `~/.claude/post-newsbytes/cache/row-<N>.json` with:

```json
{
  "row": <N>,
  "headline": "<column-C plain text>",
  "doc_url": "<column-C hyperlink target>",
  "article_url": "<column-D>",
  "post_at_local": "2026-05-11T15:00:00+08:00",
  "post_at_utc": "2026-05-11T07:00:00Z",
  "mode": "schedule"
}
```

If `mode` came back as `draft` (date in past or unparseable), surface that to the user — they may want to abort and pick a different row.

Show the parsed values and **pause for user confirmation** before going further. Drive + Bitly + SocialPilot calls all start incurring real-world side effects from Step 2 on.

### Step 2 — Fetch the Doc + image from Drive

```
python ~/.claude/post-newsbytes/run.py fetch-doc --row <N>
```

Resolves the column-C hyperlink (folder OR Doc), reads the Doc body via the Google Docs API, parses the trailing block to extract:

- **Social media text** (the caption body)
- **Key words** (comma-separated list)

Downloads the first inline image (or the first image in the folder if it's a folder) to `~/.claude/post-newsbytes/cache/row-<N>.<ext>`. Appends `social_media_text`, `keywords`, `image_path`, `image_path_ig` (the IG-resized variant) to `cache/row-<N>.json`.

If the SA can't reach the Drive folder, the script exits with `permission denied` — surface this to the user along with the SA email, and ask them to share the folder as Viewer.

### Step 3 — Shorten the article URL

```
python ~/.claude/post-newsbytes/run.py shorten --row <N>
```

POSTs to `https://api-ssl.bitly.com/v4/shorten` with the `bitly_token` from `secrets/api_keys.json`. Stores `short_url` in `cache/row-<N>.json`. On HTTP error, falls back to the full `article_url` and prints a warning — the skill continues.

### Step 3b — Share images (anyone-with-link + upload IG-resized to staging)

```
python ~/.claude/post-newsbytes/run.py share-image --row <N>
```

This is the only step that needs Drive **write** permissions. It does three things:

1. Sets anyone-with-link reader permission on the row's source image (still living in the team's Drive folder).
2. Uploads the IG-resized JPEG (`cache/row-<N>-ig.jpg`) to the staging Shared Drive folder configured in `secrets/api_keys.json` → `image_staging_folder_id`.
3. Sets anyone-with-link reader on the staged copy too.

Returns two distinct URLs in `cache/row-<N>.json`:
- `public_image_url` — `https://lh3.googleusercontent.com/d/<source-file-id>` (original .webp, used for FB/LI/X)
- `public_image_url_ig` — `https://lh3.googleusercontent.com/d/<staged-file-id>` (1080×1080 JPEG, used for IG)

If `image_staging_folder_id` is missing or the SA can't upload (e.g. it's not a Shared Drive), the IG path falls back to the source URL and warns. The Instagram post will still go up but may be auto-cropped.

### Step 4 — Build the three caption variants (you, Claude, do this)

Read `cache/row-<N>.json`. Build three caption strings according to the table above. Persist them to `cache/row-<N>-captions.json`:

```json
{
  "facebook": "<full body>\n\nRead more: <short_url>\n\n#kw1 #kw2 #broadcast #broadcasting",
  "linkedin": "<same as facebook>",
  "instagram": "<full body>\n\n<short_url>",
  "x": "<trimmed body>\n\n<short_url>\n\n#broadcast #broadcasting"
}
```

**Hashtag rules:** convert each keyword to a hashtag by stripping non-alphanumeric chars (keep ASCII letters + digits) and prefixing `#`. Multi-word keywords collapse to one hashtag (e.g. `Google Cloud` → `#GoogleCloud`). Drop empty results. Always append `#broadcast #broadcasting` last.

**X trimming rules:** total post (body + `\n\n` + URL + `\n\n` + `#broadcast #broadcasting`) must be ≤200 chars. Body, URL, and the anchor hashtags each go on their own line separated by a blank line — same multi-line layout as FB/LI, just bare URL + only the anchor hashtags. Trim the body from the end on a word boundary, then add `…` if you cut. Never truncate the URL or the two anchor hashtags.

Show all three variants to the user and **pause for approval** before posting. The user may ask you to tweak wording — apply the change to `cache/row-<N>-captions.json` and re-show.

### Step 5 — Resolve the SocialPilot APB group + per-platform accounts

Cached in `~/.claude/post-newsbytes/config.yaml` under `groups.apb` after first run. If absent:

1. Call `mcp__…__GroupList` (paged). Find the group whose name matches "Asia-Pacific Broadcasting+" (trim whitespace, case-insensitive).
2. Call `mcp__…__AccountList(groupId=<apb>)`. Collect the four `accountId`s and their `platformId`s. Map `platformId` → platform name using:
   - 1 → facebook
   - 2 → twitter (X)
   - 3 → linkedin
   - 9 → instagram
3. Write the resolved IDs back to `config.yaml`:

```yaml
groups:
  apb:
    groupId: <int>
    accounts:
      facebook:  <accountId>
      instagram: <accountId>
      linkedin:  <accountId>
      twitter:   <accountId>
```

If GroupList doesn't return an APB-named group, **stop and ask the user** for the correct group name (or to create it in SocialPilot).

### Step 6 — `CreatePost` schema (confirmed)

Confirmed via the first production run. The MCP takes one `postDescription` per call and accepts only ONE platform variant per call, so the skill **always fans out to four separate `CreatePost` invocations** — one per APB platform with that platform's caption + image URL.

Verified call shape:

```jsonc
{
  "type": "image",
  "loginIds": [<one platform's loginId from config.yaml.groups.apb.accounts>],
  "image": {
    "images": ["<public_image_url or public_image_url_ig from cache/row-<N>.json>"],
    "postDescription": "<caption variant for this platform>"
  },
  "shareType": 3,                                  // 3 = scheduled (also: 0 queue, 1 share now, 2 share next)
  "scheduleDateTime": ["YYYY-MM-DD HH:mm"]         // account-local timezone (SGT for CMG, NOT UTC)
}
```

Returns `{success: true, response: {postIds: ["<uuid>"], ...}}` on success. Capture the postId.

**Critical timezone note**: SocialPilot interprets `scheduleDateTime` in the account's configured timezone (Asia/Singapore for CMG). Pass the local time straight from `post_at_local` (e.g. `2026-05-11 16:00`) — do NOT convert to UTC. Converting would fire the post 8 hours early.

### Step 7 — Post to SocialPilot

Fire **four `CreatePost` calls in parallel** (single message with four tool-use blocks):

| Call | loginId | postDescription | images | scheduleDateTime |
|---|---|---|---|---|
| Facebook | `config.yaml.groups.apb.accounts.facebook` | `cache/row-<N>-captions.json.facebook` | `[public_image_url]` | local time, format `YYYY-MM-DD HH:mm` |
| LinkedIn | `…linkedin` | `…linkedin` | `[public_image_url]` | same |
| X | `…twitter` | `…x` | `[public_image_url]` | same |
| Instagram | `…instagram` | `…instagram` | `[public_image_url_ig]` | same |

Each call: `type: "image"`, `shareType: 3`. If `mode=draft` (date in past or unparseable), drop `scheduleDateTime` and set `shareType: 0` (queue) instead — the team can promote/schedule manually in SocialPilot.

If `image.images` is rejected (e.g. SocialPilot can't fetch the URL), retry the call as `type: "text"` with the same `postDescription` minus the image — except for Instagram, which only accepts image posts. Surface IG image failures so the team can manually attach.

Capture the returned `postId`s for the report step.

### Step 8 — Write run report (also persists post IDs to row cache)

```
python ~/.claude/post-newsbytes/run.py report --row <N> --post-ids '<json>'
```

Where `<json>` is the per-platform `{platform: postId}` map you just captured. The script:

- Persists the post IDs to `cache/row-<N>.json` under `post_ids` (so `/post-newsbytes-fetchback` can read them later).
- Writes `~/.claude/post-newsbytes/runs/post-newsbytes-<row>-YYYYMMDD.md` with row, headline, scheduled time (local + UTC), per-platform post IDs, and any warnings.

Print the report to stdout.

### Step 8.5 — Schedule the LinkedIn-URL fetchback (one-shot Cron)

After the 4 posts are queued, schedule a one-shot `CronCreate` that fires **2 minutes after the post's scheduled time** (per row, in account-local SGT). The cron's job is to invoke `/post-newsbytes-fetchback <N>`, which queries SocialPilot for the published LinkedIn permalink and writes it back to column E of the sheet.

Compute the fire time from `cache/row-<N>.json` → `post_at_local`:

```
fire_local = post_at_local + 2 minutes
cron       = "<minute> <hour> <day> <month> *"   # 5-field, no timezone conversion
```

Call:

```
CronCreate(
  cron:      "<MM> <HH> <DD> <Mon> *",
  recurring: false,                              # one-shot
  durable:   true,                               # survive Claude Code restart
  prompt:    "/post-newsbytes-fetchback <N>",
)
```

`durable: true` is important — without it the cron lives only in this Claude session and dies when Claude Code closes. With `durable: true`, the cron persists in `.claude/scheduled_tasks.json` and fires whenever the REPL is next idle at or after the fire time (catches up on missed runs).

**Heads-up to surface to the user**: the cron fires when **Claude Code is idle on this machine**. If Claude Code is closed at the scheduled fire time, it fires the next time Claude Code is re-opened. For full automation independent of Claude Code being open, the team would need to layer Windows Task Scheduler on top (future iteration).

### Step 9 — Done

Tell the user:
- The 4 posts are queued in SocialPilot for `post_at_local`.
- The fetchback cron is scheduled for `post_at_local + 2 min`.
- They can verify in SocialPilot's UI, and check column E of the sheet after the scheduled time has passed.

## Strict rules

- **Never post without showing the user the three caption variants and getting approval first.** Even in auto mode, posting to a real SocialPilot queue is a side effect on a shared system.
- **Never silently change the schedule time.** If column B can't be parsed or is in the past, surface this and let the user decide draft-vs-pick-a-new-time.
- **Never re-post a row that has already been posted in this session.** If the user re-runs `/post-newsbytes <N>` for a row whose `cache/row-<N>-captions.json` already exists, ask before re-posting (they may just want to re-render the captions for review).
- **Don't truncate the URL or the two anchor hashtags (`#broadcast #broadcasting`)** when fitting X to 200 chars.
- **Don't strip non-ASCII characters from the keyword list before hashtagging — keep them out of the hashtag** (hashtags are ASCII-only) but preserve them in the body.
- **Treat the SA key as private.** Never echo its contents. Surface its email (read from the JSON's `client_email` field) when telling the user to share a sheet/folder, but nothing else.

## File layout (under the bundle)

```
~/.claude/post-newsbytes/
├── run.py                           # CLI: collect | fetch-doc | shorten | report
├── lib/                             # auth, sheet, drive, caption helpers, shortener, image, socialpilot
├── config.yaml                      # platform IDs + cached APB group/account IDs + global hashtags
├── secrets/api_keys.json            # gitignored — bitly_token, sheet_id, tab, sa_path, timezone
├── cache/row-<N>.json               # per-row state across the four CLI steps
├── cache/row-<N>.<ext>              # downloaded image (full size)
├── cache/row-<N>-ig.<ext>           # IG-resized variant (1080×1080 padded white)
├── cache/row-<N>-captions.json      # the three caption variants (built by Claude in Step 4)
└── runs/post-newsbytes-<N>-<date>.md  # final report
```

## Re-running

`/post-newsbytes <N>` is idempotent at the read steps (collect, fetch-doc, shorten, image resize) — re-running them just refreshes the cache. The post step is **not** idempotent — re-running it will create another SocialPilot post. If you need to re-render the captions only, delete `cache/row-<N>-captions.json` and re-run from Step 4.
