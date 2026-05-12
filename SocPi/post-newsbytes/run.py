"""Single CLI entrypoint for the post-newsbytes bundle.

Usage:

  python run.py collect            --row N                       # read sheet row, parse date, write cache/row-N.json
  python run.py fetch-doc          --row N                       # follow column-C link, extract Doc body + image
  python run.py shorten            --row N                       # bit.ly the column-D article URL
  python run.py share-image        --row N                       # share source image + upload IG resize to staging, fill in public URLs (also callable directly as lib/share_image.py for the narrow Bash permission rule)
  python run.py report             --row N --post-ids JSON       # write runs/post-newsbytes-<N>-<date>.md AND persist post IDs to cache/row-N.json (for the fetchback step)
  python run.py write-linkedin-url --row N (--url U | --failed M) # fetchback writer — paste the published LinkedIn permalink (or 'FAILED — <reason>') into column E of the row

The Python side never talks to SocialPilot. The MCP CreatePost / ViewPost
calls happen in the SKILL.md runbooks. This split keeps API-touching
network work in run.py and stages Claude's per-platform reasoning + MCP
calls in the conversation.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles default to cp1252 and can't render many Unicode chars
# (non-breaking hyphens, smart quotes, emoji). Force UTF-8 with a
# replacement fallback so a cosmetic print never crashes a real step.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from lib import auth, sheet, drive, shortener, image as image_mod


def _row_cache_path(row: int) -> Path:
    return auth.cache_dir() / f"row-{row}.json"


def _load_row_cache(row: int) -> dict:
    p = _row_cache_path(row)
    if not p.exists():
        raise SystemExit(f"row cache not found: {p}. Run `collect` first for row {row}.")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_row_cache(row: int, data: dict) -> Path:
    p = _row_cache_path(row)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# collect: read one row from the sheet
# ---------------------------------------------------------------------------

def cmd_collect(args) -> int:
    secrets = auth.load_secrets()
    payload = sheet.read_row(secrets, args.row)
    out = _save_row_cache(args.row, payload)
    print(f"collect: row {args.row} — \"{payload['headline']}\"")
    print(f"  date (local): {payload['post_at_local']}")
    print(f"  date (UTC):   {payload['post_at_utc']}")
    print(f"  mode:         {payload['mode']}")
    print(f"  doc_url:      {payload['doc_url']}")
    print(f"  article_url:  {payload['article_url']}")
    print(f"wrote: {out}")
    return 0


# ---------------------------------------------------------------------------
# fetch-doc: follow column-C link, extract Doc + image
# ---------------------------------------------------------------------------

def cmd_fetch_doc(args) -> int:
    secrets = auth.load_secrets()
    cached = _load_row_cache(args.row)
    if not cached.get("doc_url"):
        raise SystemExit("doc_url missing from row cache — re-run `collect`")
    parsed = drive.fetch(secrets, cached["doc_url"], args.row)
    cached.update({
        "social_media_text": parsed["social_media_text"],
        "keywords": parsed["keywords"],
        "image_path": parsed["image_path"],
        "drive_image_id": parsed.get("drive_image_id", ""),
    })
    if parsed.get("image_path"):
        ig_path = image_mod.resize_for_instagram(Path(parsed["image_path"]))
        cached["image_path_ig"] = str(ig_path)
    out = _save_row_cache(args.row, cached)
    print(f"fetch-doc: row {args.row}")
    body = cached["social_media_text"] or ""
    print(f"  social_media_text ({len(body)} chars):")
    snippet = body[:160].replace("\n", " ")
    print(f"    {snippet}{'...' if len(body) > 160 else ''}")
    print(f"  keywords ({len(cached['keywords'])}): {cached['keywords']}")
    print(f"  image_path:    {cached.get('image_path') or '(no image found)'}")
    print(f"  image_path_ig: {cached.get('image_path_ig') or '(skipped)'}")
    print(f"wrote: {out}")
    return 0


# ---------------------------------------------------------------------------
# shorten: bit.ly the column-D article URL
# ---------------------------------------------------------------------------

def cmd_shorten(args) -> int:
    secrets = auth.load_secrets()
    cached = _load_row_cache(args.row)
    article_url = cached.get("article_url")
    if not article_url:
        raise SystemExit("article_url missing from row cache — re-run `collect`")
    short = shortener.shorten(secrets, article_url)
    cached["short_url"] = short or article_url
    cached["short_url_fallback"] = short is None
    out = _save_row_cache(args.row, cached)
    if short:
        print(f"shorten: row {args.row} — {article_url} -> {short}")
    else:
        print(f"shorten: row {args.row} — bit.ly failed, falling back to full URL")
    print(f"wrote: {out}")
    return 0


# ---------------------------------------------------------------------------
# share-image: dispatch to lib/share_image.py via subprocess so the same
# narrow permission rule (Bash python lib/share_image.py *) covers this
# subcommand. Direct invocation of lib/share_image.py from the command
# line also works — both paths use the same code.
# ---------------------------------------------------------------------------

def cmd_share_image(args) -> int:
    import subprocess
    script = Path(__file__).resolve().parent / "lib" / "share_image.py"
    return subprocess.call([sys.executable, str(script), "--row", str(args.row)])


# ---------------------------------------------------------------------------
# write-linkedin-url: fetchback writer — paste the LinkedIn permalink
# (or a FAILED marker) into column E of the source sheet.
# ---------------------------------------------------------------------------

def cmd_write_linkedin_url(args) -> int:
    if not args.url and not args.failed:
        raise SystemExit("must supply --url <permalink> or --failed <reason>")
    if args.url and args.failed:
        raise SystemExit("--url and --failed are mutually exclusive")
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    ws = sh.worksheet(secrets["tab"])
    value = args.url if args.url else f"FAILED — {args.failed}"
    # Column E = the LinkedIn URL column.
    ws.update_acell(f"E{args.row}", value)
    cached = _load_row_cache(args.row)
    cached["linkedin_url_written"] = value
    cached["linkedin_url_written_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_row_cache(args.row, cached)
    print(f"write-linkedin-url: row {args.row} column E set to: {value}")
    return 0


# ---------------------------------------------------------------------------
# report: write the run summary
# ---------------------------------------------------------------------------

def cmd_report(args) -> int:
    cached = _load_row_cache(args.row)
    try:
        post_ids = json.loads(args.post_ids) if args.post_ids else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--post-ids must be valid JSON: {exc}")
    # Persist the post IDs to the row cache so the fetchback step (which
    # may run in a fresh Claude session triggered by Cron) can read them.
    if post_ids:
        cached["post_ids"] = post_ids
        _save_row_cache(args.row, cached)
    runs_dir = auth.runs_dir()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = runs_dir / f"post-newsbytes-{args.row}-{today}.md"
    lines: list[str] = []
    lines.append(f"# /post-newsbytes — row {args.row}")
    lines.append("")
    lines.append(f"- **Headline**: {cached.get('headline', '')}")
    lines.append(f"- **Article URL**: {cached.get('article_url', '')}")
    lines.append(f"- **Short URL**: {cached.get('short_url', '')}")
    lines.append(f"- **Scheduled (local)**: {cached.get('post_at_local', '')}")
    lines.append(f"- **Scheduled (UTC)**: {cached.get('post_at_utc', '')}")
    lines.append(f"- **Mode**: {cached.get('mode', '')}")
    lines.append("")
    lines.append("## Per-platform results")
    lines.append("")
    if post_ids:
        for platform, post_id in post_ids.items():
            lines.append(f"- **{platform}**: postId `{post_id}`")
    else:
        lines.append("(no post IDs supplied)")
    warnings = []
    if cached.get("short_url_fallback"):
        warnings.append("bit.ly failed — caption posted with full article URL")
    if cached.get("mode") == "draft":
        warnings.append("date in column B was past or unparseable — posted as draft")
    if not cached.get("image_path"):
        warnings.append("no image found in the Drive folder/Doc — posted caption-only")
    if warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: wrote {out}")
    print("")
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("collect", help="Read one row from the configured sheet")
    sp.add_argument("--row", type=int, required=True, help="Sheet row number (1-indexed; row 1 is the header)")
    sp.set_defaults(handler=cmd_collect)

    sp = sub.add_parser("fetch-doc", help="Follow the column-C Drive link and extract the Doc + image")
    sp.add_argument("--row", type=int, required=True)
    sp.set_defaults(handler=cmd_fetch_doc)

    sp = sub.add_parser("shorten", help="Shorten the column-D article URL via Bitly")
    sp.add_argument("--row", type=int, required=True)
    sp.set_defaults(handler=cmd_shorten)

    sp = sub.add_parser("share-image", help="Share source image + upload IG resize to staging Shared Drive")
    sp.add_argument("--row", type=int, required=True)
    sp.set_defaults(handler=cmd_share_image)

    sp = sub.add_parser("write-linkedin-url", help="Fetchback writer — paste the LinkedIn permalink (or FAILED marker) into column E")
    sp.add_argument("--row", type=int, required=True)
    sp.add_argument("--url", default="", help="Published LinkedIn permalink (mutually exclusive with --failed)")
    sp.add_argument("--failed", default="", help="Failure reason (will be written as 'FAILED — <reason>')")
    sp.set_defaults(handler=cmd_write_linkedin_url)

    sp = sub.add_parser("report", help="Write the run report markdown")
    sp.add_argument("--row", type=int, required=True)
    sp.add_argument("--post-ids", default="", help='JSON object: {"facebook": <id>, "instagram": <id>, ...}')
    sp.set_defaults(handler=cmd_report)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except auth.SecretsError as exc:
        print(f"secrets error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
