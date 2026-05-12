"""Auth + secrets loader for post-newsbytes.

Reads `secrets/api_keys.json`, returns gspread + google-api clients.
Reuses the SocPi service-account key by default (same path the Sales
bundle reuses) so the team only manages one key.

Never prints secret values.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

BUNDLE_ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = BUNDLE_ROOT / "secrets" / "api_keys.json"

DEFAULT_SA_PATH = "~/.claude/skills/if-exclusives-audit/secrets/gsheets-sa.json"
DEFAULT_TIMEZONE = "Asia/Singapore"
DEFAULT_GROUP = "Asia-Pacific Broadcasting+"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive",  # full Drive — needed to upload IG-resized to staging Shared Drive + set anyone-with-link
]


class SecretsError(RuntimeError):
    pass


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        raise SecretsError(
            f"Missing {SECRETS_PATH}. Copy api_keys.json.example next to it and fill in the values."
        )
    payload = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    required = ("bitly_token", "sheet_id", "tab", "sa_path", "image_staging_folder_id")
    missing = [k for k in required if not payload.get(k) or str(payload[k]).startswith("<paste")]
    if missing:
        raise SecretsError(
            f"Fill in {SECRETS_PATH}; still placeholder for: {missing}. "
            "image_staging_folder_id requires a Google Shared Drive folder — "
            "see INSTALL.md Step 4b."
        )
    payload.setdefault("timezone", DEFAULT_TIMEZONE)
    payload.setdefault("default_group", DEFAULT_GROUP)
    return payload


def _sa_path(secrets: dict) -> Path:
    raw = secrets.get("sa_path") or DEFAULT_SA_PATH
    sa_path = Path(os.path.expanduser(raw))
    if not sa_path.exists():
        raise SecretsError(f"Service account key not found at {sa_path}")
    return sa_path


def gspread_client(secrets: dict | None = None) -> gspread.Client:
    s = secrets or load_secrets()
    return gspread.service_account(filename=str(_sa_path(s)))


def open_sheet(secrets: dict | None = None):
    s = secrets or load_secrets()
    return gspread_client(s).open_by_key(s["sheet_id"])


def google_credentials(secrets: dict | None = None) -> Credentials:
    """Service-account credentials usable with the Google Docs + Drive API clients."""
    s = secrets or load_secrets()
    return Credentials.from_service_account_file(str(_sa_path(s)), scopes=GOOGLE_SCOPES)


def cache_dir() -> Path:
    p = BUNDLE_ROOT / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runs_dir() -> Path:
    p = BUNDLE_ROOT / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p
