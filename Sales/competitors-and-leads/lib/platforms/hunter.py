"""Hunter.io domain search client. Mirrors n8n p2-hunter."""
from __future__ import annotations

import requests

ENDPOINT = "https://api.hunter.io/v2/domain-search"


def domain_search(api_key: str, domain: str, *, limit: int = 10,
                  department: str = "marketing,communication",
                  timeout: int = 30) -> dict:
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": limit,
        "department": department,
    }
    r = requests.get(ENDPOINT, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def domain_from_url(url: str) -> str:
    d = (url or "").lower()
    for prefix in ("https://", "http://", "www."):
        d = d.replace(prefix, "")
    return d.split("/")[0]
