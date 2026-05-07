"""Save an MCP tool response to a per-run file, auto-routing by loginId.

Two modes:

1. **Explicit path** (legacy):
       cat resp.json | python save_mcp_response.py <out-path>

2. **Auto-route** (preferred — eliminates manual filename mapping):
       cat resp.json | python save_mcp_response.py --auto \\
           --run-dir cache/responses/<RUN_ID> \\
           --account-map cache/account_map.json \\
           --kind delivered          # or 'queued'

   The script inspects the first record's `loginId`, looks it up in
   account_map.json to get (publication, platform), and writes to
   `<run-dir>/<pub>__<platform>__<kind>.json`.

This lets the orchestrator fire many parallel MCP calls and pipe each
response straight into this saver without tracking which call was which.

Bulk mode (process many tool-results files at once):
       python save_mcp_response.py --bulk-dir <tool-results-dir> \\
           --run-dir cache/responses/<RUN_ID> \\
           --account-map cache/account_map.json \\
           --kind delivered

   Reads every *.txt / *.json in the dir, auto-routes each.
"""

import argparse
import json
import re
import sys
from pathlib import Path


PLATFORM_BY_ID = {1: "facebook", 2: "twitter", 3: "linkedin", 9: "instagram"}


def extract_envelope(text: str) -> dict | list:
    """Return the inner SocialPilot envelope from raw response text.

    Handles three shapes:
      1. Direct envelope: {"success":true,"data":[...]} or {"posts":[...]}
      2. MCP-wrapped:    [{"type":"text","text":"<envelope-json>"}]
      3. Nested string:  whole thing JSON-encoded as a single string
    """
    text = text.strip()
    payload = json.loads(text)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "text" in item:
                try:
                    return json.loads(item["text"])
                except Exception:
                    pass
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            pass
    return payload


def first_record(env) -> dict | None:
    if isinstance(env, dict):
        for k in ("data", "posts"):
            v = env.get(k)
            if isinstance(v, list) and v:
                return v[0]
    return None


def route(env, account_map: dict, kind: str) -> tuple[str, str] | None:
    """Return (publication, platform) for a response envelope, or None if no records.

    Uses loginId from the first record, looking up in account_map.
    Falls back to platformId on the record itself for the platform.
    """
    rec = first_record(env)
    if not rec:
        return None
    login_id = rec.get("loginId")
    platform_id = rec.get("platformId")
    if login_id is None:
        return None
    login_id = int(login_id)
    for pub, info in account_map.items():
        for plat, lid in (info.get("accounts") or {}).items():
            if lid is not None and int(lid) == login_id:
                if platform_id and PLATFORM_BY_ID.get(int(platform_id)) and \
                        PLATFORM_BY_ID[int(platform_id)] != plat:
                    # account-map and record disagree — trust the record
                    plat = PLATFORM_BY_ID[int(platform_id)]
                return pub, plat
    # Unknown loginId — try platformId alone with no pub
    if platform_id:
        return ("unknown", PLATFORM_BY_ID.get(int(platform_id), "unknown"))
    return None


def save_one(text: str, run_dir: Path, account_map: dict, kind: str) -> Path | None:
    try:
        env = extract_envelope(text)
    except Exception as e:
        print(f"  skip: not JSON ({e})", file=sys.stderr)
        return None
    routed = route(env, account_map, kind)
    if not routed:
        # Empty response — still save under a placeholder so we know it ran.
        return None
    pub, plat = routed
    out = run_dir / f"{pub}__{plat}__{kind}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the inner envelope (not the MCP wrapper) for the aggregator.
    out.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  routed -> {out.name}", file=sys.stderr)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_path", nargs="?",
                    help="Explicit output path (legacy single-file mode)")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-route a single stdin response by loginId")
    ap.add_argument("--bulk-dir",
                    help="Process every file in this dir as separate responses")
    ap.add_argument("--run-dir",
                    help="Per-run output directory (for --auto / --bulk-dir)")
    ap.add_argument("--account-map",
                    help="Path to account_map.json (for --auto / --bulk-dir)")
    ap.add_argument("--kind", choices=("delivered", "queued"),
                    help="Response kind tag (for --auto / --bulk-dir / --auto-flat)")
    ap.add_argument("--auto-flat", action="store_true",
                    help="Save a per-article response (any pubs/platforms) "
                         "as a single slug-keyed file. Aggregator derives "
                         "pub/platform from each record.")
    ap.add_argument("--slug",
                    help="Article slug (used with --auto-flat for the filename)")
    ap.add_argument("--auto-batch", action="store_true",
                    help="Read a JSON array of {slug, kind, response} entries "
                         "(from --input <file> or stdin) and save them all in "
                         "one shot. Avoids the 38-shell-startups problem when "
                         "saving many responses sequentially.")
    ap.add_argument("--input",
                    help="Path to a JSON file holding the --auto-batch array. "
                         "Preferred over stdin: one Write call to disk, one "
                         "Bash call to process — no giant heredocs.")
    args = ap.parse_args()

    # Auto-batch mode: one payload (file OR stdin), many output files.
    if args.auto_batch:
        if not args.run_dir:
            print("--auto-batch requires --run-dir", file=sys.stderr)
            sys.exit(2)
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.input:
            try:
                raw_text = Path(args.input).read_text(encoding="utf-8",
                                                     errors="replace")
            except Exception as e:
                print(f"ERROR: cannot read --input {args.input}: {e}",
                      file=sys.stderr)
                sys.exit(1)
        else:
            raw_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        try:
            entries = json.loads(raw_text)
        except Exception as e:
            src = args.input or "stdin"
            print(f"ERROR: {src} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(entries, list):
            print("ERROR: --auto-batch expects a JSON array", file=sys.stderr)
            sys.exit(1)
        n_ok = 0
        n_skip = 0
        for entry in entries:
            if not isinstance(entry, dict):
                n_skip += 1; continue
            slug = entry.get("slug")
            kind = entry.get("kind")
            response = entry.get("response")
            if not (slug and kind in ("delivered", "queued") and response is not None):
                n_skip += 1; continue
            # `response` may be either an envelope dict or a string of JSON.
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except Exception:
                    n_skip += 1; continue
            try:
                env = extract_envelope(json.dumps(response)) \
                      if not isinstance(response, dict) else response
            except Exception:
                n_skip += 1; continue
            wrapped = {"_kind": kind, "_slug": slug, "envelope": env}
            out = run_dir / f"{slug}__{kind}.json"
            out.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            n_ok += 1
        print(f"batch: saved {n_ok} files (skipped {n_skip}) -> {run_dir}",
              file=sys.stderr)
        return

    # Auto-flat mode: per-article query, all platforms in one file.
    if args.auto_flat:
        if not (args.run_dir and args.kind and args.slug):
            print("--auto-flat requires --run-dir, --kind, --slug",
                  file=sys.stderr)
            sys.exit(2)
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            env = extract_envelope(text)
        except Exception as e:
            print(f"ERROR: not JSON ({e})", file=sys.stderr)
            sys.exit(1)
        # Wrap with kind tag so aggregator knows posted vs scheduled.
        wrapped = {"_kind": args.kind, "_slug": args.slug, "envelope": env}
        out = run_dir / f"{args.slug}__{args.kind}.json"
        out.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        # Count records for visibility.
        rec = first_record(env)
        n = 0
        if isinstance(env, dict):
            for k in ("data", "posts"):
                v = env.get(k)
                if isinstance(v, list):
                    n = len(v); break
        print(f"  flat -> {out.name} ({n} records)", file=sys.stderr)
        return

    # Bulk mode: scan a directory, route every file.
    if args.bulk_dir:
        if not (args.run_dir and args.account_map and args.kind):
            print("--bulk-dir requires --run-dir, --account-map, --kind",
                  file=sys.stderr)
            sys.exit(2)
        run_dir = Path(args.run_dir)
        amap = json.loads(Path(args.account_map).read_text(encoding="utf-8"))
        bulk = Path(args.bulk_dir)
        n_ok = 0
        for f in sorted(bulk.iterdir()):
            if not f.is_file():
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if save_one(txt, run_dir, amap, args.kind):
                n_ok += 1
        print(f"bulk: routed {n_ok} files into {run_dir}", file=sys.stderr)
        return

    raw = sys.stdin.buffer.read()
    text = raw.decode("utf-8", errors="replace")

    # Auto-route mode (single response on stdin).
    if args.auto:
        if not (args.run_dir and args.account_map and args.kind):
            print("--auto requires --run-dir, --account-map, --kind",
                  file=sys.stderr)
            sys.exit(2)
        run_dir = Path(args.run_dir)
        amap = json.loads(Path(args.account_map).read_text(encoding="utf-8"))
        if save_one(text, run_dir, amap, args.kind):
            return
        print("ERROR: could not route response (no records or unknown loginId)",
              file=sys.stderr)
        sys.exit(1)

    # Legacy explicit-path mode.
    if not args.out_path:
        print("usage: save_mcp_response.py <out-path>  (or --auto / --bulk-dir)",
              file=sys.stderr)
        sys.exit(2)
    out = Path(args.out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        json.loads(text)
    except Exception as e:
        print(f"ERROR: stdin is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    out.write_text(text, encoding="utf-8")
    print(f"saved -> {out} ({len(text)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
