"""Single CLI entrypoint for the competitors-and-leads bundle.

Usage:

  python run.py phase1-collect [--dry-run] [--out PATH]
  python run.py phase1-write   --input PATH                 # JSON: {"competitors":[{...},...]}

  python run.py phase2-collect [--dry-run] [--out PATH]
  python run.py phase2-write   --input PATH                 # JSON: {"pocs":[{...}], "competitors_with_no_pocs":[...]}

  python run.py phase3-collect [--dry-run] [--out PATH]
  python run.py phase3-write   --input PATH                 # JSON: {"competitor_name_lower": {website_research_summary,...}, ...}

  python run.py phase4-collect [--dry-run] [--out PATH]     # alias for old "phase a"
  python run.py phase4-write   --input PATH                 # JSON: {"drafts":[{...}]}

  python run.py drafts-status                                # how many candidates remain (Phase 4)
  python run.py drafts-tone-examples [--out PATH]            # pull current Revised Version exemplars

The split keeps API-touching steps separate from LLM reasoning so each
SKILL.md runbook can stage Claude's work cleanly: collect -> reason ->
write. The runbooks under skills/<name>/SKILL.md are the source of
truth for which subcommands belong to which phase.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from lib import auth, phase1_competitors, phase2_pocs, phase3_research, phase4_drafts, writers


def _default_out(name: str) -> Path:
    return auth.output_dir() / f"{name}.json"


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

def cmd_phase1_collect(args) -> int:
    out = Path(args.out) if args.out else _default_out("phase1_competitors_context")
    payload = phase1_competitors.collect(dry_run=args.dry_run)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    candidates = payload.get("candidates", [])
    print(f"phase1-collect{' (dry-run)' if args.dry_run else ''}: {len(candidates)} client candidate(s)")
    print(f"wrote: {out}")
    return 0


def cmd_phase1_write(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    competitors = payload.get("competitors", [])
    if not competitors:
        print("no 'competitors' array in input")
        return 1
    summary = writers.write_competitors(competitors)
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def cmd_phase2_collect(args) -> int:
    out = Path(args.out) if args.out else _default_out("phase2_pocs_context")
    payload = phase2_pocs.collect(dry_run=args.dry_run)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    candidates = payload.get("candidates", [])
    print(f"phase2-collect{' (dry-run)' if args.dry_run else ''}: {len(candidates)} competitor candidate(s)")
    print(f"wrote: {out}")
    return 0


def cmd_phase2_write(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    pocs = payload.get("pocs", [])
    no_pocs = payload.get("competitors_with_no_pocs", [])
    summary = writers.write_pocs(pocs, no_pocs)
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Phase 3
# ---------------------------------------------------------------------------

def cmd_phase3_collect(args) -> int:
    out = Path(args.out) if args.out else _default_out("phase3_research_context")
    payload = phase3_research.collect(dry_run=args.dry_run)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    candidates = payload.get("candidates", [])
    print(f"phase3-collect{' (dry-run)' if args.dry_run else ''}: {len(candidates)} competitor candidate(s)")
    print(f"wrote: {out}")
    return 0


def cmd_phase3_write(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = writers.write_research(payload)
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Phase 4 (drafting)
# ---------------------------------------------------------------------------

def cmd_phase4_collect(args) -> int:
    out = Path(args.out) if args.out else _default_out("phase4_drafts_context")
    payload = phase4_drafts.collect(dry_run=args.dry_run)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    pocs = payload.get("pocs", [])
    print(f"phase4-collect{' (dry-run)' if args.dry_run else ''}: {len(pocs)} POC candidate(s)")
    if pocs and args.dry_run:
        from collections import Counter
        per_comp = Counter(p["competitor_name"] for p in pocs)
        for comp, cnt in per_comp.most_common():
            print(f"  {cnt:>3}  {comp}")
    print(f"wrote: {out}")
    return 0


def cmd_phase4_write(args) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    drafts = payload.get("drafts", [])
    if not drafts:
        print("no 'drafts' array in input")
        return 1
    summary = writers.write_drafts(drafts)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_drafts_status(args) -> int:
    secrets = auth.load_secrets()
    sh = auth.open_sheet(secrets)
    pocs = phase4_drafts.list_candidates(sh)
    print(f"phase4 candidates remaining: {len(pocs)}")
    return 0


def cmd_drafts_tone_examples(args) -> int:
    out = Path(args.out) if args.out else _default_out("revised_examples")
    sh = auth.open_sheet()
    rows = sh.worksheet("Email Drafts").get_all_records()
    revised = []
    for r in rows:
        rv = (r.get("Revised Version") or "").strip()
        if rv:
            revised.append({
                "competitor": r.get("Competitor Name", ""),
                "poc_name": r.get("POC Name", ""),
                "poc_title": r.get("POC Title", ""),
                "subject": r.get("Email Subject", ""),
                "revised_body": rv,
            })
    out.write_text(json.dumps({"revised_drafts": revised}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"revised exemplars: {len(revised)}, wrote: {out}")
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_collect(name, handler):
        sp = sub.add_parser(name)
        sp.add_argument("--dry-run", action="store_true",
                        help="List candidates without hitting external APIs")
        sp.add_argument("--out", help="Output JSON path (default: output/<name>.json)")
        sp.set_defaults(handler=handler)
        return sp

    def add_write(name, handler):
        sp = sub.add_parser(name)
        sp.add_argument("--input", required=True, help="Input JSON file path")
        sp.set_defaults(handler=handler)
        return sp

    add_collect("phase1-collect", cmd_phase1_collect)
    add_write("phase1-write", cmd_phase1_write)
    add_collect("phase2-collect", cmd_phase2_collect)
    add_write("phase2-write", cmd_phase2_write)
    add_collect("phase3-collect", cmd_phase3_collect)
    add_write("phase3-write", cmd_phase3_write)
    add_collect("phase4-collect", cmd_phase4_collect)
    add_write("phase4-write", cmd_phase4_write)

    sub.add_parser("drafts-status").set_defaults(handler=cmd_drafts_status)

    sp = sub.add_parser("drafts-tone-examples")
    sp.add_argument("--out", help="Output JSON path (default: output/revised_examples.json)")
    sp.set_defaults(handler=cmd_drafts_tone_examples)

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
