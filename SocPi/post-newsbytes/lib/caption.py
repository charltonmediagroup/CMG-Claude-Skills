"""Build the per-platform caption variants.

Claude does this in conversation per Step 4 of the SKILL.md, but the
helpers here exist so that the same rules can be unit-tested and so a
deterministic Python fallback is available if Claude ever needs to
preview the captions outside a conversation.

Rules (mirror SKILL.md):

  Default (Facebook + LinkedIn):
    <body>
    <blank>
    Read more: <short_url>
    <blank>
    #kw1 #kw2 ... #broadcast #broadcasting

  Instagram:
    <body>
    <blank>
    <short_url>          (no "Read more:" prefix)
    (no hashtags)

  X (Twitter):
    <trimmed body>
    <blank>
    <short_url>
    <blank>
    #broadcast #broadcasting
    Total ≤200 chars (counting the blank-line separators). Body trims
    from the end on a word boundary, then a '…' is appended.
"""
from __future__ import annotations

import re

ANCHOR_HASHTAGS = "#broadcast #broadcasting"
X_MAX_CHARS = 200

_HASHTAG_CLEAN_RE = re.compile(r"[^A-Za-z0-9]+")

# Word-doc artefacts (non-breaking hyphens, smart quotes, em-dashes) that
# render unpredictably across social platforms. Normalize to plain ASCII
# before building captions. Note: the trimming-marker '…' that
# build_x_caption appends is added *after* normalization, so it survives.
_ASCII_FOLD = {
    "‐": "-",   # hyphen
    "‑": "-",   # non-breaking hyphen — the one that bit us in the first run
    "‒": "-",   # figure dash
    "–": "-",   # en-dash
    "—": "--",  # em-dash
    "―": "--",  # horizontal bar
    "“": '"',   # smart double quote (open)
    "”": '"',   # smart double quote (close)
    "„": '"',   # double low-9 quote
    "‘": "'",   # smart single quote (open)
    "’": "'",   # smart single quote (close) / apostrophe
    "‚": "'",   # single low-9 quote
    "…": "...", # horizontal ellipsis
    " ": " ",   # non-breaking space
    " ": " ",   # thin space
    "​": "",    # zero-width space
}


def _normalize_ascii(text: str) -> str:
    """Map common Word-doc Unicode artefacts to plain ASCII equivalents.

    Leaves any other Unicode (accents, non-Latin scripts, emoji) untouched —
    only targets the specific characters that cause cross-platform rendering
    surprises.
    """
    if not text:
        return ""
    for src, dst in _ASCII_FOLD.items():
        if src in text:
            text = text.replace(src, dst)
    return text


def _to_hashtag(keyword: str) -> str | None:
    cleaned = _HASHTAG_CLEAN_RE.sub("", keyword or "")
    return f"#{cleaned}" if cleaned else None


def _hashtags_for_keywords(keywords: list[str]) -> str:
    tags = []
    for kw in keywords:
        tag = _to_hashtag(kw)
        if tag:
            tags.append(tag)
    tags.append("#broadcast")
    tags.append("#broadcasting")
    return " ".join(tags)


def build_default_caption(body: str, short_url: str, keywords: list[str]) -> str:
    body = (body or "").strip()
    hashtags = _hashtags_for_keywords(keywords or [])
    return f"{body}\n\nRead more: {short_url}\n\n{hashtags}".strip()


def build_instagram_caption(body: str, short_url: str) -> str:
    body = (body or "").strip()
    return f"{body}\n\n{short_url}".strip()


def build_x_caption(body: str, short_url: str) -> str:
    body = (body or "").strip()
    suffix = f"\n\n{short_url}\n\n{ANCHOR_HASHTAGS}"
    budget = X_MAX_CHARS - len(suffix)
    if budget <= 0:
        # Pathological case: even just the URL + anchors + separators
        # exceed 200. Return what we can and let SocialPilot validate.
        return f"{short_url}\n\n{ANCHOR_HASHTAGS}"
    if len(body) <= budget:
        return f"{body}{suffix}"
    cut = body[:budget].rstrip()
    # Trim back to the last whitespace boundary so we don't slice mid-word.
    space = cut.rfind(" ")
    if space > budget * 0.6:  # keep at least ~60% of the budget
        cut = cut[:space].rstrip()
    return f"{cut}…{suffix}"


def build_all(body: str, short_url: str, keywords: list[str]) -> dict:
    # Normalize once up front so all four variants share the same clean body.
    # The trimming marker '…' that build_x_caption appends is added *after*
    # this point, so it isn't folded to '...'.
    body = _normalize_ascii(body)
    default = build_default_caption(body, short_url, keywords)
    return {
        "facebook": default,
        "linkedin": default,
        "instagram": build_instagram_caption(body, short_url),
        "x": build_x_caption(body, short_url),
    }
