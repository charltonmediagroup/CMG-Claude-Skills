"""Match articles to SocialPilot posts (delivered + queued).

Inputs:
  articles.json  — output of fetch_articles.py
  posts.json     — output of aggregate_posts.py (each post has kind = "posted"|"scheduled")

Output:
  matches.json   — per-article: matches per platform separated by kind, fuzzy flags

URL-first matching with caption-URL extraction, short-link resolution, and a
fuzzy slug↔caption fallback. Each match is tagged with kind so downstream
report.py + write_to_sheet.py can render posted permalinks vs SCHEDULED markers
distinctly.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import requests
from rapidfuzz import fuzz


SHORTLINK_HOSTS = {
    "bit.ly", "t.co", "lnkd.in", "ow.ly", "buff.ly",
    "tinyurl.com", "socialpilot.co", "spi.cx", "lnk.bio",
}

DROP_QUERY_PARAMS = re.compile(
    r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|igshid|si|ref|ref_src|ref_url)$",
    re.IGNORECASE,
)

URL_REGEX = re.compile(r"https?://[^\s<>()\"'\]]+", re.IGNORECASE)

PLATFORMS = ("facebook", "instagram", "linkedin", "twitter")


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    if not p.scheme:
        return url.strip().lower()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
          if not DROP_QUERY_PARAMS.match(k)]
    qs.sort()
    return urlunparse(("https", host, path, "", urlencode(qs), ""))


def resolve_shortlink(url: str, cache: dict) -> str:
    if url in cache:
        return cache[url]
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        cache[url] = url
        return url
    if host not in SHORTLINK_HOSTS:
        cache[url] = url
        return url
    try:
        r = requests.head(url, allow_redirects=True, timeout=5,
                          headers={"User-Agent": "Mozilla/5.0 if-exclusives-audit"})
        final = r.url or url
    except Exception:
        final = url
    cache[url] = final
    return final


def extract_urls_from_text(text: str) -> list[str]:
    if not text:
        return []
    return [m.group(0).rstrip(".,);:!?") for m in URL_REGEX.finditer(text)]


def slug_to_words(slug: str) -> str:
    return re.sub(r"[-_/]+", " ", slug or "").strip()


def empty_buckets() -> dict:
    return {p: [] for p in PLATFORMS}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("articles")
    ap.add_argument("posts")
    ap.add_argument("--shortlinks", default=None)
    ap.add_argument("--fuzzy-threshold", type=int, default=85)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    articles = json.loads(Path(args.articles).read_text(encoding="utf-8"))
    posts = json.loads(Path(args.posts).read_text(encoding="utf-8"))

    shortlinks_path = Path(args.shortlinks) if args.shortlinks else None
    shortlink_cache: dict[str, str] = {}
    if shortlinks_path and shortlinks_path.exists():
        shortlink_cache = json.loads(shortlinks_path.read_text(encoding="utf-8"))

    norm_to_idx: dict[str, int] = {}
    by_pub: dict[str, list[int]] = {}
    by_slug: dict[str, list[int]] = {}  # slug -> [article indices]
    for i, a in enumerate(articles):
        a["norm_url"] = normalize_url(a["url"])
        norm_to_idx[a["norm_url"]] = i
        by_pub.setdefault(a["publication"], []).append(i)
        slug = (a.get("slug") or "").strip().lower()
        if slug:
            by_slug.setdefault(slug, []).append(i)
        a.setdefault("title", a.get("title_guess") or a["url"])
        a.setdefault("tag", "IF/EXCLUSIVE")
        # Two buckets per platform: posted_matches and scheduled_matches.
        a["posted_matches"] = empty_buckets()
        a["scheduled_matches"] = empty_buckets()
        a["fuzzy_matches"] = empty_buckets()  # only fuzzy fallback hits

    bare_re = re.compile(
        r"(?<![\w./@:])((?:www\.)?[a-z0-9-]+\.(?:com|net|hk|asia|co\.uk|com\.au|media|sg)/[\w./?#&=%-]+)",
        re.IGNORECASE,
    )

    for post in posts:
        platform = post.get("platform")
        if platform not in PLATFORMS:
            continue
        kind = post.get("kind") or "posted"
        bucket_name = "scheduled_matches" if kind == "scheduled" else "posted_matches"

        desc = post.get("description") or ""
        post_pub = (post.get("publication") or "").lower().lstrip("www.")
        post_url = post.get("postUrl") or ""

        # Fast path: postUrl alone matches an article — skip caption parsing.
        if post_url:
            pu_norm = normalize_url(post_url)
            if pu_norm in norm_to_idx:
                idx = norm_to_idx[pu_norm]
                articles[idx][bucket_name][platform].append({
                    "postId": post.get("postId"),
                    "publishedAt": post.get("publishedAt") or post.get("postDate"),
                    "scheduled_at": post.get("scheduled_at") or "",
                    "permalink": post.get("permalink") or "",
                    "headline": post.get("headline") or "",
                    "description": desc,
                })
                continue

        # Slug fallback: when postUrl is empty (Instagram, or trimmed-by-orchestrator
        # responses) AND the post's caption mentions any article slug we know about,
        # claim it. The per-slug MCP query guarantees the slug is somewhere in the
        # response, so this is safe even when the caption was stripped.
        desc_lower = desc.lower()
        slug_hit_idx = None
        for slug, idxs in by_slug.items():
            if slug and slug in desc_lower:
                # Prefer an article whose publication matches the post's pub.
                same_pub = [i for i in idxs
                            if articles[i]["publication"].lower().lstrip("www.") == post_pub]
                slug_hit_idx = same_pub[0] if same_pub else idxs[0]
                break
        if slug_hit_idx is not None:
            articles[slug_hit_idx][bucket_name][platform].append({
                "postId": post.get("postId"),
                "publishedAt": post.get("publishedAt") or post.get("postDate"),
                "scheduled_at": post.get("scheduled_at") or "",
                "permalink": post.get("permalink") or "",
                "headline": post.get("headline") or "",
                "description": desc,
            })
            continue

        urls_in_post: list[str] = extract_urls_from_text(desc)
        if post_url:
            urls_in_post.append(post_url)
        for m in bare_re.finditer(desc):
            urls_in_post.append("https://" + m.group(1))

        resolved = [normalize_url(resolve_shortlink(u, shortlink_cache))
                    for u in urls_in_post]

        matched = False
        added_for_this_post: set[int] = set()
        for r_norm in resolved:
            if r_norm in norm_to_idx:
                idx = norm_to_idx[r_norm]
                if idx in added_for_this_post:
                    continue
                articles[idx][bucket_name][platform].append({
                    "postId": post.get("postId"),
                    "publishedAt": post.get("publishedAt") or post.get("postDate"),
                    "scheduled_at": post.get("scheduled_at") or "",
                    "permalink": post.get("permalink") or "",
                    "headline": post.get("headline") or "",
                    "description": desc,
                })
                added_for_this_post.add(idx)
                matched = True

        if matched:
            continue

        # Fuzzy fallback — same publication only.
        candidates = by_pub.get(post_pub) or []
        best_idx, best_score = None, 0
        for idx in candidates:
            words = slug_to_words(articles[idx]["slug"])
            if not words:
                continue
            score = fuzz.token_set_ratio(words, desc)
            if score > best_score:
                best_score, best_idx = score, idx
        if best_idx is not None and best_score >= args.fuzzy_threshold:
            articles[best_idx]["fuzzy_matches"][platform].append({
                "postId": post.get("postId"),
                "kind": kind,
                "publishedAt": post.get("publishedAt") or post.get("postDate"),
                "scheduled_at": post.get("scheduled_at") or "",
                "permalink": post.get("permalink") or "",
                "description": desc,
                "score": best_score,
            })

    if shortlinks_path:
        shortlinks_path.parent.mkdir(parents=True, exist_ok=True)
        shortlinks_path.write_text(json.dumps(shortlink_cache, indent=2),
                                   encoding="utf-8")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(articles, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Wrote matches for {len(articles)} articles to {args.out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
