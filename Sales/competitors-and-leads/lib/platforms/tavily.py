"""Tavily client. Used in Phase 2 (LinkedIn URL discovery, team page, contacts).

Mirrors the n8n p2-tavily-* HTTP nodes.
"""
from __future__ import annotations

import requests

ENDPOINT = "https://api.tavily.com/search"


def search(api_key: str, query: str, *, search_depth: str = "basic",
           include_answer: bool = False, max_results: int = 5,
           timeout: int = 15) -> dict:
    body = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "max_results": max_results,
    }
    r = requests.post(ENDPOINT, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def find_linkedin_company_url(api_key: str, competitor_name: str,
                              competitor_website: str) -> str | None:
    """Mirrors the JS in n8n p2-extract-linkedin: search Tavily for a
    LinkedIn /company/<slug> URL preferring matches that include the
    domain keyword.
    """
    domain = (competitor_website or "").lower()
    for prefix in ("https://", "http://", "www."):
        domain = domain.replace(prefix, "")
    domain = domain.split("/")[0]
    domain_keyword = domain.split(".")[0] if domain else ""

    query = f"{competitor_name} OR {domain} linkedin company site:linkedin.com/company"
    payload = search(api_key, query, max_results=5)

    import re
    pat = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[a-z0-9._-]+")

    fallback = None
    for r in payload.get("results", []) or []:
        url = (r.get("url") or "").lower()
        m = pat.search(url)
        if not m:
            continue
        cleaned = m.group(0).rstrip(".")
        normalized = re.sub(r"(?:[a-z]{2,3}\.)?linkedin\.com", "www.linkedin.com", cleaned, count=1)
        if not normalized.endswith("/"):
            normalized += "/"
        if domain_keyword and domain_keyword in normalized:
            return normalized
        if not fallback:
            fallback = normalized
    return fallback
