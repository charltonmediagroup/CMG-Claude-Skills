"""SerpAPI client. Used in Phase 1 (competitor discovery) and Phase 3 (research)."""
from __future__ import annotations

import requests

ENDPOINT = "https://serpapi.com/search.json"


def search(api_key: str, query: str, *, gl: str | None = None,
           num: int = 10, timeout: int = 20) -> dict:
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "google_domain": "google.com",
        "hl": "en",
        "device": "desktop",
        "num": num,
    }
    if gl:
        params["gl"] = gl
    r = requests.get(ENDPOINT, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def organic_summaries(payload: dict) -> list[dict]:
    out = []
    for r in (payload.get("organic_results") or []):
        out.append({
            "title": r.get("title"),
            "link": r.get("link"),
            "snippet": r.get("snippet"),
        })
    return out
