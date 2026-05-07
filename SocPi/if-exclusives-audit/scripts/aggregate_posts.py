"""Aggregate per-run SocialPilot response files into a flat posts.json.

Run-dir layout the orchestrator builds (one file per pub × platform × kind):

  cache/responses/<run-id>/
    asianbankingandfinance.net__facebook__delivered.json
    asianbankingandfinance.net__facebook__queued.json
    asianbankingandfinance.net__instagram__delivered.json
    asianbankingandfinance.net__instagram__queued.json
    ...

Each file is the raw MCP DeliveredPosts/QueuedPosts response (the SocialPilot
JSON envelope: {success, message, data: [...], total, page}).

Output `posts.json` is a flat list of:
  {publication, platform, kind, loginId, postId, postUrl, permalink,
   postDate, scheduled_at, description}
  - kind = "posted" | "scheduled"
  - scheduled_at populated only when kind == "scheduled"
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_envelope(path: Path) -> tuple[list[dict], str | None]:
    """Load a saved MCP response file and return (records, kind_override).

    `kind_override` is set if the file is in `--auto-flat` shape
    ({"_kind": "delivered|queued", "envelope": {...}}); otherwise None and
    the caller derives kind from the filename.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception as e:
        print(f"  skip {path.name}: {e}", file=sys.stderr)
        return [], None

    # Auto-flat wrapper from save_mcp_response.py --auto-flat:
    # {"_kind": "delivered|queued", "_slug": "...", "envelope": {...}}
    kind_override = None
    if isinstance(payload, dict) and "_kind" in payload and "envelope" in payload:
        kind_override = payload["_kind"]
        payload = payload["envelope"]

    def _items(env: dict) -> list:
        for k in ("data", "posts"):
            v = env.get(k)
            if isinstance(v, list):
                return v
        return []

    if isinstance(payload, dict) and ("data" in payload or "posts" in payload):
        return _items(payload), kind_override
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "text" in item:
                try:
                    inner = json.loads(item["text"])
                except Exception:
                    continue
                if isinstance(inner, dict) and ("data" in inner or "posts" in inner):
                    return _items(inner), kind_override
    return [], kind_override


# Strict filename pattern: <pub>__<plat>__<kind>.json (legacy per-pub-platform flow)
FNAME_RE = re.compile(r"^(?P<pub>[^_]+(?:\.[^_]+)*?)__(?P<plat>facebook|instagram|linkedin|twitter)__(?P<kind>delivered|queued)\.json$")
# Loose filename pattern: <slug>__<kind>.json (new per-article flow)
FNAME_FLAT_RE = re.compile(r"^(?P<slug>.+?)__(?P<kind>delivered|queued)\.json$")
# SocialPilot uses TWO different code spaces. Don't mix them up.
PLATFORM_BY_PLATFORMID = {1: "facebook", 2: "twitter", 3: "linkedin", 9: "instagram"}
# `accountId` on post records uses internal type codes (NOT platformIds):
#   1 = Twitter/X, 5 = Facebook page, 9 = LinkedIn, 25 = Instagram business
PLATFORM_BY_ACCOUNTID = {1: "twitter", 5: "facebook", 9: "linkedin", 25: "instagram"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True,
                    help="Directory holding per-run response files")
    ap.add_argument("--account-map", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"ERROR: run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(2)

    account_map = json.loads(Path(args.account_map).read_text(encoding="utf-8"))
    # loginId -> (publication, platform) — used as a sanity check, not primary
    login_index: dict[int, tuple[str, str]] = {}
    for pub, info in account_map.items():
        for plat, login_id in (info.get("accounts") or {}).items():
            if login_id is not None:
                login_index[int(login_id)] = (pub, plat)

    posts: list[dict] = []
    seen_ids: set[str] = set()
    by_pp_kind: dict[tuple[str, str, str], int] = {}
    # Drop counters for loud diagnostic output.
    drop_no_postid = 0
    drop_dup_postid = 0
    drop_no_loginid = 0
    drop_unknown_pub_plat = 0
    total_records_seen = 0

    for path in sorted(run_dir.iterdir()):
        if not path.is_file() or not path.name.endswith(".json"):
            continue

        # Try strict pattern first (legacy per-pub-platform), then loose flat.
        m_strict = FNAME_RE.match(path.name)
        m_flat = None if m_strict else FNAME_FLAT_RE.match(path.name)
        if not (m_strict or m_flat):
            print(f"  skip (bad name): {path.name}", file=sys.stderr)
            continue

        pub_from_name = m_strict.group("pub") if m_strict else None
        plat_from_name = m_strict.group("plat") if m_strict else None
        kind_from_name = (m_strict or m_flat).group("kind")

        records, kind_override = load_envelope(path)
        kind = "posted" if (kind_override or kind_from_name) == "delivered" else "scheduled"

        for p in records:
            if not isinstance(p, dict):
                continue
            total_records_seen += 1
            pid = p.get("postId")
            if not pid:
                drop_no_postid += 1
                continue
            if pid in seen_ids:
                drop_dup_postid += 1
                continue
            seen_ids.add(pid)

            login_id = p.get("loginId")
            platform_id_raw = p.get("platformId")
            account_id_raw = p.get("accountId")

            # Strict-name flow: trust filename, cross-check loginId.
            # Flat-name flow: derive pub/platform from each record.
            if pub_from_name:
                pub = pub_from_name
                plat = plat_from_name
                if login_id:
                    idx_match = login_index.get(int(login_id))
                    if idx_match and idx_match != (pub, plat):
                        print(f"  WARN loginId {login_id} maps to {idx_match} "
                              f"but file says {(pub, plat)}; trusting filename",
                              file=sys.stderr)
            else:
                # Per-record derivation (auto-flat / per-article flow).
                # 1. loginId lookup is the most reliable for both pub AND platform.
                # 2. platformId (1/2/3/9) overrides if present and disagrees.
                # 3. accountId (1/5/9/25) is the next fallback — uses a SEPARATE
                #    code space, so it has its own mapping.
                pub = "unknown"
                plat = "unknown"
                if login_id:
                    idx_match = login_index.get(int(login_id))
                    if idx_match:
                        pub, plat = idx_match
                if platform_id_raw and int(platform_id_raw) in PLATFORM_BY_PLATFORMID:
                    plat = PLATFORM_BY_PLATFORMID[int(platform_id_raw)]
                elif plat == "unknown" and account_id_raw \
                        and int(account_id_raw) in PLATFORM_BY_ACCOUNTID:
                    plat = PLATFORM_BY_ACCOUNTID[int(account_id_raw)]
                if pub == "unknown" or plat == "unknown":
                    if not login_id:
                        drop_no_loginid += 1
                    else:
                        drop_unknown_pub_plat += 1
                    continue

            scheduled_at = ""
            if kind == "scheduled":
                # SocialPilot uses scheduleDateUtc / postTimeFormat / postDate
                # for queued posts. Prefer postTimeFormat (ISO-ish "YYYY-MM-DD HH:MM"),
                # falling back to postDate (human-readable).
                scheduled_at = (
                    p.get("postTimeFormat")
                    or p.get("scheduleDateUtc")
                    or p.get("postDate")
                    or ""
                )

            # Headline preference: postTitle > first sentence of postDesc.
            headline = (p.get("postTitle") or "").strip()
            if not headline:
                desc_first = (p.get("postDesc") or "").strip().split("\n", 1)[0]
                # Strip trailing URL fragment if the first line ends with one.
                headline = re.sub(r"\s+https?://\S+\s*$", "", desc_first).strip()
            # Cap at 120 chars so cells don't get unwieldy.
            if len(headline) > 120:
                headline = headline[:117].rstrip() + "…"

            posts.append({
                "publication": pub,
                "platform": plat,
                "kind": kind,
                "loginId": login_id,
                "postId": pid,
                "postUrl": p.get("postUrl") or "",
                "permalink": p.get("redirectUrl") or "",
                "headline": headline,
                "postDate": p.get("postDate") or p.get("postTimeFormat") or "",
                "scheduled_at": scheduled_at,
                "description": p.get("postDesc") or "",
            })
            by_pp_kind[(pub, plat, kind)] = by_pp_kind.get((pub, plat, kind), 0) + 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(posts, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    print(f"Aggregated {len(posts)} posts from {run_dir}", file=sys.stderr)
    posted = sum(v for k, v in by_pp_kind.items() if k[2] == "posted")
    scheduled = sum(v for k, v in by_pp_kind.items() if k[2] == "scheduled")
    print(f"  posted: {posted}, scheduled: {scheduled}", file=sys.stderr)
    for (pub, plat, kind), n in sorted(by_pp_kind.items()):
        print(f"  {pub:35s} {plat:10s} {kind:10s} {n}", file=sys.stderr)

    # Loud diagnostics — surface dropped records so the orchestrator can
    # self-correct without a human noticing.
    total_dropped = (drop_no_postid + drop_no_loginid + drop_unknown_pub_plat)
    if total_dropped:
        print("", file=sys.stderr)
        print(f"!!! DROPPED {total_dropped}/{total_records_seen} RECORDS !!!",
              file=sys.stderr)
        if drop_no_postid:
            print(f"  - {drop_no_postid:4d} missing postId  "
                  "(orchestrator likely trimmed responses; postId is REQUIRED)",
                  file=sys.stderr)
        if drop_no_loginid:
            print(f"  - {drop_no_loginid:4d} missing loginId "
                  "(orchestrator likely trimmed responses; loginId is REQUIRED)",
                  file=sys.stderr)
        if drop_unknown_pub_plat:
            print(f"  - {drop_unknown_pub_plat:4d} loginId not in account_map "
                  "(legit cross-pub post or stale account_map.json)",
                  file=sys.stderr)
        if drop_no_postid or drop_no_loginid:
            print("", file=sys.stderr)
            print("FIX: re-save responses WITHOUT trimming. The aggregator needs "
                  "postId, loginId, accountId/platformId, postUrl, postDesc, "
                  "redirectUrl, postDate at minimum. Pass raw MCP envelopes to "
                  "save_mcp_response.py --auto-batch verbatim.",
                  file=sys.stderr)
            sys.exit(3)
    if drop_dup_postid:
        print(f"  (deduped {drop_dup_postid} duplicate postIds — expected for "
              "cross-pub or repeat queries)", file=sys.stderr)


if __name__ == "__main__":
    main()
