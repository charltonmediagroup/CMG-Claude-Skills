"""Bitly URL shortener.

POST https://api-ssl.bitly.com/v4/shorten with the team's Bitly access
token (free tier — bitly.com → Profile → API → Generate Access Token).

Returns the short URL on success, None on any error so the caller can
fall back to the full URL gracefully.
"""
from __future__ import annotations

import json

import requests

BITLY_ENDPOINT = "https://api-ssl.bitly.com/v4/shorten"
TIMEOUT_SECONDS = 12


def shorten(secrets: dict, long_url: str) -> str | None:
    token = secrets.get("bitly_token") or ""
    if not token or token.startswith("<paste"):
        print("[shortener] no bitly_token in secrets/api_keys.json")
        return None
    body = {"long_url": long_url}
    if secrets.get("bitly_group_guid"):
        body["group_guid"] = secrets["bitly_group_guid"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            BITLY_ENDPOINT,
            data=json.dumps(body),
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"[shortener] network error: {exc}")
        return None
    if resp.status_code in (200, 201):
        try:
            return resp.json().get("link")
        except ValueError:
            print("[shortener] could not parse Bitly response as JSON")
            return None
    print(f"[shortener] Bitly returned HTTP {resp.status_code}: {resp.text[:300]}")
    return None
