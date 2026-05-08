"""Apify client. Used in Phase 2 for LinkedIn employee + profile scraping.

Mirrors n8n p2-apify1 (harvestapi/linkedin-company-employees) and
p2-apify2 (harvestapi/linkedin-profile-scraper).
"""
from __future__ import annotations

import requests

EMPLOYEES_ACT = "harvestapi~linkedin-company-employees"
PROFILES_ACT = "harvestapi~linkedin-profile-scraper"


def _run_sync(act: str, token: str, body: dict, *, timeout: int = 120) -> list[dict]:
    url = f"https://api.apify.com/v2/acts/{act}/run-sync-get-dataset-items?token={token}"
    r = requests.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


APAC_LOCATIONS = [
    "Asia", "Singapore", "Hong Kong", "India", "Australia", "Japan",
    "South Korea", "Philippines", "Malaysia", "Thailand", "Indonesia",
    "Vietnam", "New Zealand", "Taiwan",
]
MARKETING_TITLES = [
    "Marketing", "Communications", "Paid Media", "Digital Media",
    "Field Marketing", "Demand Generation",
]


def get_company_employees(token: str, linkedin_company_url: str, *,
                          max_items: int = 20) -> list[dict]:
    body = {
        "companies": [linkedin_company_url],
        "maxItems": max_items,
        "locations": APAC_LOCATIONS,
        "jobTitles": MARKETING_TITLES,
    }
    return _run_sync(EMPLOYEES_ACT, token, body, timeout=180)


def enrich_profiles(token: str, profile_urls: list[str]) -> list[dict]:
    if not profile_urls:
        return []
    body = {
        "profileScraperMode": "Profile details + email search ($10 per 1k)",
        "queries": profile_urls,
    }
    return _run_sync(PROFILES_ACT, token, body, timeout=180)
