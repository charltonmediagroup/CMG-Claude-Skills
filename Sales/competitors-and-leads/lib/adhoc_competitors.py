"""Ad-hoc competitor collector. Powers /find-similar-companies.

Single-shot version of phase1_competitors: takes the source company + free-text
kind from CLI args (not the SBR sheet) and emits a context payload for Claude.
Claude does the WebSearch reasoning step itself, then drafts go to the
Companies tab via adhoc_writers.write_companies().
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def collect(*, company_name: str, company_kind: str,
            region: str | None = None, max_count: int = 10) -> dict:
    return {
        "generated_at": date.today().isoformat(),
        "input": {
            "company_name": company_name.strip(),
            "company_kind": company_kind.strip(),
            "region": (region or "").strip() or "Global",
            "max_count": int(max_count),
        },
    }


def write_context(payload: dict, out_path: Path) -> None:
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
