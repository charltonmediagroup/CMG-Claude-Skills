#!/usr/bin/env python3
"""Print the next empty row in column A of the target tab (1-indexed).

Returns the first gap in column A, scanning from top. Falls back to
len(col_A) + 1 if no internal gap exists.

Usage:
    python sheet_next_empty_row.py --sa secrets/gsheets-sa.json \
        --sheet-id <id> --tab "<tab>"
"""
import argparse
import sys

import gspread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", required=True)
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--skip-rows", type=int, default=3,
                    help="Skip the first N rows (header + section markers). Default 3.")
    args = ap.parse_args()

    gc = gspread.service_account(filename=args.sa)
    sh = gc.open_by_key(args.sheet_id)
    ws = sh.worksheet(args.tab)
    col = ws.col_values(1)  # column A; trailing blanks stripped by gspread

    # Look for first internal gap after the skip-rows region.
    for i in range(args.skip_rows, len(col)):
        if not col[i].strip():
            print(i + 1)  # convert 0-index to 1-indexed row
            return
    # No internal gap — append after the last filled row.
    print(len(col) + 1)


if __name__ == "__main__":
    main()
