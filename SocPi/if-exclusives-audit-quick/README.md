# if-exclusives-audit-quick

Lightweight companion to the main `if-exclusives-audit` skill. Skips the RSS-feed URL collection step (Step 1a) and just runs the audit on whatever URLs are already in column A of the "IF & Exclusives" sheet.

## When to use it

Invoke `/if-exclusives-audit-quick` (instead of `/if-exclusives-audit`) when:

- ✅ You've **manually pasted URLs** into column A and want them audited as-is, not wiped.
- ✅ You've **already run the main skill** and just want to re-check the same URL list (e.g. after the social team posted things).
- ✅ The **RSS feeds are flaky** today and you don't want feed errors to block the audit.
- ❌ You want fresh URLs from the feeds → use `/if-exclusives-audit` instead.

## Dependency on the main skill

This skill **does not contain its own scripts, secrets, or cache**. It piggybacks on `~/.claude/skills/if-exclusives-audit/` for all of that.

When porting to a new machine, install **both** folders:
```
~/.claude/skills/if-exclusives-audit/         ← main, has scripts + secrets + cache
~/.claude/skills/if-exclusives-audit-quick/   ← this skill, just SKILL.md
```

If only this skill is installed, it'll fail when it tries to `cd` into the main skill's folder.

## Setup

Already done if you set up `if-exclusives-audit`. Just drop this folder into `~/.claude/skills/`.

## Differences from the main skill at a glance

| Step | Main skill | Quick skill |
|---|---|---|
| 1a — Scrape RSS feeds + populate column A | ✅ runs | ❌ **skipped** |
| 1b — Read column A into articles.json | ✅ | ✅ |
| 2 — Account map | ✅ | ✅ |
| 3 — SocialPilot per-article fetch | ✅ | ✅ |
| 4 — Aggregate posts | ✅ | ✅ |
| 5 — Match articles ↔ posts | ✅ | ✅ |
| 6 — Markdown / CSV report | ✅ | ✅ |
| 7 — Write back to sheet (D-H + feed report rows) | ✅ | ✅ |

Total saved: ~10-60s depending on RSS feed health (the slow `sbr.com.sg/in-focus-articles.xml` alone can take 30-60s).
