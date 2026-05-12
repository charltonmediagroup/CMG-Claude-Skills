---
name: post-newsbytes-fetchback
description: After a post-newsbytes row has been published by SocialPilot, fetch the resulting LinkedIn permalink and write it back to column E of the "Weekly NewsBytes Engagement [CMG]" sheet. Designed to be invoked by the one-shot Cron scheduled at the end of /post-newsbytes — fires at post_at_local + 2 minutes per row, reads the cached LinkedIn postId from cache/row-<N>.json, calls SocialPilot's ViewPost MCP for the published URL, and runs `python run.py write-linkedin-url --row N --url <permalink>`. Falls back to `--failed "<reason>"` if SocialPilot still reports the post as scheduled/errored. Use when invoked as /post-newsbytes-fetchback <row> (typically by the Cron, but the user can also run it manually after a delayed publish).
---

# /post-newsbytes-fetchback — Write LinkedIn permalink back to column E

Runs after a `/post-newsbytes` row's scheduled time has passed. One row per invocation. Triggered automatically by the durable Cron that `/post-newsbytes` schedules in its Step 8.5; can also be invoked manually for debugging.

## Where the code lives

`~/.claude/post-newsbytes/` — same bundle as `/post-newsbytes`. This skill is just a runbook; the actual sheet write happens via `python run.py write-linkedin-url`.

## Source of truth (strict)

- The LinkedIn `postId` was captured during `/post-newsbytes`'s Step 8 (`report` subcommand persisted the per-platform `post_ids` map to `~/.claude/post-newsbytes/cache/row-<N>.json`).
- The sheet ID + tab name come from `~/.claude/post-newsbytes/secrets/api_keys.json`.
- Column E = LinkedIn URL on the source sheet.

## Execution flow

### Step 0 — Parse invocation

Read `$ARGUMENTS`. Expect a single integer row number. If absent or non-numeric, stop and ask.

### Step 1 — Load cached state

Read `~/.claude/post-newsbytes/cache/row-<N>.json`. Pull:

- `post_ids.linkedin` — the SocialPilot postId UUID returned by CreatePost for the LinkedIn account
- `headline` — for log context

If `post_ids.linkedin` is missing, abort with a clear error: the row was probably never posted, or `report` was never run.

### Step 2 — Query SocialPilot for the post

Call `mcp__…__ViewPost(postId=<linkedin postId>)`.

**Confirmed response shape** (verified May 11, 2026 against the Setplex row's published LinkedIn post — keep this in sync if SocialPilot ever changes its payload):

```jsonc
{
  "success": true,
  "data": {
    "postStatus": "Y",                                          // "Y" = published, "S" = scheduled, "F" = failed (best guess)
    "redirectUrl": "https://www.linkedin.com/feed/update/urn:li:share:<id>",  // ← THE permalink to use
    "postUrl": "",                                              // empty for LinkedIn (also empty for IG, populated for FB/X)
    "postDesc": "<full caption>",
    "accountId": 9,                                             // 9 = LinkedIn (5 = FB, 1 = X, 25 = IG)
    "accountUsername": "APB+ (Asia-Pacific Broadcasting+)",
    "scheduleDateUtc": "May 11, 2026 04:00 PM",                 // local-time string, NOT UTC despite the field name
    "postDate": "May 11, 2026 04:00 PM",
    "loginId": 2078329,
    // ...many more fields, ignore
  }
}
```

**Use `data.redirectUrl` as the permalink** — `postUrl` is empty for LinkedIn (matches the audit skill's documented behavior). This is the field to write into column E.

### Step 3 — Branch on post status

- **If `postStatus == "Y"` and `redirectUrl` is non-empty** (published, permalink known): run
  ```
  python ~/.claude/post-newsbytes/run.py write-linkedin-url --row <N> --url "<redirectUrl>"
  ```
- **If `postStatus == "S"`** (still scheduled — cron fired before SocialPilot actually published, e.g. publishing was delayed > 2 min): run
  ```
  python ~/.claude/post-newsbytes/run.py write-linkedin-url --row <N> --failed "PENDING — still scheduled at fetchback time"
  ```
  AND surface to the user: "row <N> not yet published — re-run `/post-newsbytes-fetchback <N>` in 5 minutes."
- **If `postStatus == "F"` or the response indicates error**: run
  ```
  python ~/.claude/post-newsbytes/run.py write-linkedin-url --row <N> --failed "<reason from ViewPost>"
  ```

### Step 4 — Confirm

Read back column E by running the CLI's output, OR just trust the `write-linkedin-url: row <N> column E set to: <value>` printout. Done.

## Strict rules

- **Only LinkedIn** for now. Even though the row also has FB/IG/X postIds in cache, this skill writes only column E.
- **Never call CreatePost from here.** Read-only against SocialPilot — this skill only queries existing posts.
- **Don't crash if column E was already filled.** Re-runs are idempotent — overwrite is fine.

## Re-running

`/post-newsbytes-fetchback <N>` is idempotent — column E gets overwritten with whatever ViewPost currently reports. If you re-ran the parent `/post-newsbytes` and got new postIds, the cache now has the latest set; fetchback picks them up automatically.
