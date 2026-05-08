"""Auth + secrets loader.

Reads `secrets/api_keys.json` and returns gspread + dict of API keys.
Never prints secret values.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import gspread

# Bundle root -- the directory containing this lib/
BUNDLE_ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = BUNDLE_ROOT / "secrets" / "api_keys.json"


class SecretsError(RuntimeError):
    pass


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        raise SecretsError(
            f"Missing {SECRETS_PATH}. Copy api_keys.json.example next to it and fill in the values."
        )
    payload = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    required = ("serpapi", "tavily", "apify", "hunter", "sheet_id", "sa_path")
    missing = [k for k in required if not payload.get(k) or str(payload[k]).startswith("<paste")]
    if missing:
        raise SecretsError(f"Fill in {SECRETS_PATH}; still placeholder for: {missing}")
    return payload


def gspread_client(secrets: dict | None = None) -> gspread.Client:
    s = secrets or load_secrets()
    sa_path = Path(os.path.expanduser(s["sa_path"]))
    if not sa_path.exists():
        raise SecretsError(f"Service account key not found at {sa_path}")
    return gspread.service_account(filename=str(sa_path))


def open_sheet(secrets: dict | None = None):
    s = secrets or load_secrets()
    return gspread_client(s).open_by_key(s["sheet_id"])


def output_dir() -> Path:
    p = BUNDLE_ROOT / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p
