"""SocialPilot — discovery notes + helpers.

The actual MCP tool calls happen in SKILL.md (Claude invokes
`mcp__…__GroupList`, `mcp__…__AccountList`, `mcp__…__CreatePost`).
Python doesn't have direct access to those MCP tools, so this module is
a) a docstring-style record of the discovered schema, and
b) helpers for caching the resolved group/account IDs in config.yaml.

`CreatePost` schema — to be filled in by the first run of the skill.
The existing audit skills only call read-side tools (DeliveredPosts,
QueuedPosts, GroupList, AccountList), so the write-side schema is
unknown until first contact.

How to discover the schema (Step 6 of the SKILL.md):
1. Invoke `mcp__…__CreatePost` with no arguments.
2. The MCP returns a validation error listing required fields.
3. Iterate: add one field at a time, re-invoke, read the next error,
   until you have a successful (or rejected-for-content) call.
4. Append the discovered shape to this docstring.

Provisional shape (to verify):
    {
      "accounts":  [<accountId>, ...],     // four APB accountIds, or one per call
      "message":   "<caption>",            // post body
      "media":     [<URL or base64>, ...], // optional — schema unknown
      "scheduledAt": "ISO 8601 UTC",       // null/absent => post now
      "status":    "draft" | "scheduled" | "publish",
    }

If the MCP requires per-platform variants in separate calls, fan out to
4 calls — one per accountId, each with that platform's caption + image.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from lib import auth

CONFIG_PATH = auth.BUNDLE_ROOT / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def cached_apb_group() -> dict | None:
    cfg = load_config()
    return ((cfg.get("groups") or {}).get("apb")) or None


def cache_apb_group(group_id: str | int, accounts: dict[str, int]) -> None:
    """Persist the resolved APB group + per-platform accountIds.

    `group_id` can be a UUID string (SocialPilot returns these) or an int.
    `accounts` is a dict like {"facebook": 1234, "instagram": 5678, ...}.
    """
    cfg = load_config()
    cfg.setdefault("groups", {})
    cfg["groups"]["apb"] = {
        "groupId": str(group_id),
        "accounts": {k: int(v) for k, v in accounts.items()},
    }
    save_config(cfg)


PLATFORM_BY_PLATFORMID = {
    1: "facebook",
    2: "twitter",
    3: "linkedin",
    9: "instagram",
}


def platform_for(platform_id: int) -> str | None:
    return PLATFORM_BY_PLATFORMID.get(int(platform_id))
