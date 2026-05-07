#!/usr/bin/env python3
"""Write a single row to A, B, C, D, G of the target tab via batch_update.

Usage:
    python sheet_write_row.py --sa secrets/gsheets-sa.json \
        --sheet-id <id> --tab "<tab>" --row 59 \
        --magazine "Singapore Business Review" --by AI \
        --summary "..." --url "https://..." \
        --questions "Q1\\n\\nQ2\\n\\nQ3..."

The --summary and --questions strings may contain literal "\\n" sequences;
they will be converted to real newlines before writing.
"""
import argparse
import sys

import gspread


def unescape_newlines(s):
    return (s or "").replace("\\n", "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--magazine", required=True, help="Column A — full publication name")
    ap.add_argument("--by", default="AI", help="Column B — source marker. Default 'AI'.")
    ap.add_argument("--summary", required=True, help="Column C — one-paragraph summary")
    ap.add_argument("--url", required=True, help="Column D — article URL")
    ap.add_argument("--questions", required=True,
                    help="Column G — questions joined by '\\n\\n' (literal or real newlines)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print intended write but don't commit")
    args = ap.parse_args()

    summary = unescape_newlines(args.summary)
    questions = unescape_newlines(args.questions)

    if args.dry_run:
        print(f"DRY RUN row={args.row} on tab {args.tab!r}")
        print(f"  A: {args.magazine}")
        print(f"  B: {args.by}")
        print(f"  C ({len(summary)}c): {summary[:120]}...")
        print(f"  D: {args.url}")
        print(f"  G ({len(questions)}c): {questions[:160]}...")
        return

    gc = gspread.service_account(filename=args.sa)
    sh = gc.open_by_key(args.sheet_id)
    ws = sh.worksheet(args.tab)

    ws.batch_update([
        {"range": f"A{args.row}", "values": [[args.magazine]]},
        {"range": f"B{args.row}", "values": [[args.by]]},
        {"range": f"C{args.row}", "values": [[summary]]},
        {"range": f"D{args.row}", "values": [[args.url]]},
        {"range": f"G{args.row}", "values": [[questions]]},
    ])
    print(f"OK wrote row {args.row} on {args.tab!r}")


if __name__ == "__main__":
    main()
