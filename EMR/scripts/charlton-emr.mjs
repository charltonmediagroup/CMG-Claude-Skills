#!/usr/bin/env node
// Charlton B2B Earned Media Report — Drupal sitemap walker + filter
//
// Walks a Charlton Media B2B publication's Drupal sitemap (/sitemap.xml index +
// paginated pages), drops sponsored URLs by pattern, keeps URLs whose slug
// contains a brand keyword, fetches each, parses JSON-LD for date/title, applies
// a title+body keyword filter, and writes a JSON dataset that the companion
// skill turns into a DOCX report.
//
// Usage:
//   node EMR/scripts/charlton-emr.mjs \
//     --site SBR \
//     --brand "DBS" \
//     --keywords "DBS,POSB,DBS Vickers"
//
// Sites:
//   SBR | HKB | ABF | ABR | RA  (see SITES table below)
//
// Optional flags:
//   --output-dir EMR/output           (default; brand cache lands in <dir>/<SITE>/.cache/)
//   --rate-ms 250                     delay between sitemap-page requests
//   --concurrency 6                   parallel article fetches
//   --max-body-chars 350              filter window into article body
//   --max-sitemap-pages 200           hard cap on sitemap pagination

import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

const SITES = {
  SBR: {
    domain: 'sbr.com.sg',
    publication: 'Singapore Business Review',
    titleSuffixRe: /\s*[|\-–]\s*Singapore\s*Business\s*Review.*$/i,
  },
  HKB: {
    domain: 'hongkongbusiness.hk',
    publication: 'Hong Kong Business',
    titleSuffixRe: /\s*[|\-–]\s*Hong\s*Kong\s*Business.*$/i,
  },
  ABF: {
    domain: 'asianbankingandfinance.net',
    publication: 'Asian Banking & Finance',
    titleSuffixRe: /\s*[|\-–]\s*Asian\s*Banking\s*(?:&|and|&amp;)\s*Finance.*$/i,
  },
  ABR: {
    domain: 'asianbusinessreview.com',
    publication: 'Asian Business Review',
    titleSuffixRe: /\s*[|\-–]\s*Asian\s*Business\s*Review.*$/i,
  },
  RA: {
    domain: 'retailasia.com',
    publication: 'Retail Asia',
    titleSuffixRe: /\s*[|\-–]\s*Retail\s*Asia.*$/i,
  },
};

// URL second-segment → report taxon. Falls back to 'Sectors'.
const URL_TYPE_TO_TAXON = {
  'people':         'Appointments',
  'event-news':     'Events',
  'feature':        'Features',
  'features':       'Features',
  'interview':      'Interviews',
  'interviews':     'Interviews',
  'news':           'News',
  'more-news':      'News',
  'exclusives':     'Exclusives',
  'exclusive':      'Exclusives',
  'reports':        'News',
  'co-written':     'Features',
};

function parseArgs(argv) {
  const args = {
    site: null,
    brand: null,
    keywords: null,
    outputDir: 'EMR/output',
    rateMs: 1500,
    concurrency: 6,
    maxBodyChars: 350,
    maxSitemapPages: 200,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case '--site': args.site = next(); break;
      case '--brand': args.brand = next(); break;
      case '--keywords': args.keywords = next(); break;
      case '--output-dir': args.outputDir = next(); break;
      case '--rate-ms': args.rateMs = Number(next()); break;
      case '--concurrency': args.concurrency = Number(next()); break;
      case '--max-body-chars': args.maxBodyChars = Number(next()); break;
      case '--max-sitemap-pages': args.maxSitemapPages = Number(next()); break;
      case '-h': case '--help':
        printHelp(); process.exit(0);
      default:
        console.error(`Unknown flag: ${a}`); process.exit(2);
    }
  }
  if (!args.site || !args.brand || !args.keywords) {
    console.error('--site, --brand and --keywords are required');
    printHelp();
    process.exit(2);
  }
  args.site = args.site.toUpperCase();
  if (!SITES[args.site]) {
    console.error(`Unknown --site "${args.site}". Valid: ${Object.keys(SITES).join(', ')}`);
    process.exit(2);
  }
  args.keywordList = args.keywords.split(',').map(s => s.trim()).filter(Boolean);
  return args;
}

function printHelp() {
  console.log(`Usage:
  node EMR/scripts/charlton-emr.mjs --site <SBR|HKB|ABF|ABR|RA> --brand "DBS" --keywords "DBS,POSB,..."

Required:
  --site         One of: ${Object.keys(SITES).join(', ')}
                 Maps to: ${Object.entries(SITES).map(([k, v]) => `${k}=${v.domain}`).join(', ')}
  --brand        Brand name (used as report label and slug for output filenames)
  --keywords     Comma-separated keyword list (parent + sub-brands). An article is kept
                 only if (a) its URL slug contains at least one keyword AND (b) at least
                 one keyword appears in the title or first N chars of body.

Optional:
  --output-dir       Directory for JSON outputs (default: EMR/output; cache lands in <dir>/<SITE>/.cache/)
  --rate-ms          Delay between sitemap-page requests (default: 1500)
  --concurrency      Parallel article fetches (default: 6)
  --max-body-chars   Body window for keyword filter (default: 350)
  --max-sitemap-pages  Sitemap pagination cap (default: 200)
`);
}

function slugify(s) {
  return s.toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

function decodeEntities(s) {
  if (!s) return '';
  return s
    .replace(/&#8217;|&rsquo;/g, '’')
    .replace(/&#8216;|&lsquo;/g, '‘')
    .replace(/&#8220;|&ldquo;/g, '“')
    .replace(/&#8221;|&rdquo;/g, '”')
    .replace(/&#8211;|&ndash;/g, '–')
    .replace(/&#8212;|&mdash;/g, '—')
    .replace(/&#8230;|&hellip;/g, '…')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const backoffMs = (attempt) => Math.min(2000 * Math.pow(2, attempt), 15000);

async function fetchHtml(url, { timeoutMs = 30000, retries = 2 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        headers: {
          'User-Agent': UA,
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
          'Accept-Language': 'en-US,en;q=0.9',
        },
        signal: ac.signal,
      });
      clearTimeout(t);
      if (!res.ok) {
        lastErr = new Error(`HTTP ${res.status}`);
        if (res.status >= 500 && attempt < retries) { await sleep(backoffMs(attempt)); continue; }
        if (res.status === 403 && attempt < retries) { await sleep(backoffMs(attempt)); continue; }
        throw lastErr;
      }
      return await res.text();
    } catch (e) {
      clearTimeout(t);
      lastErr = e;
      if (attempt < retries) await sleep(backoffMs(attempt));
    }
  }
  throw lastErr;
}

function extractSitemapLocs(xml) {
  const out = [];
  const re = /<loc>([^<]+)<\/loc>/g;
  let m;
  while ((m = re.exec(xml)) !== null) out.push(m[1].trim());
  return out;
}

async function walkSitemap(domain, { rateMs, maxSitemapPages }) {
  const indexUrl = `https://${domain}/sitemap.xml`;
  const indexXml = await fetchHtml(indexUrl, { timeoutMs: 30000, retries: 3 });
  // The Drupal sitemap_generator emits a <sitemapindex> with <sitemap><loc>...</loc>.
  // extractSitemapLocs returns every <loc> regardless of whether it's an index entry
  // or a urlset entry, so we differentiate by URL pattern.
  const indexLocs = extractSitemapLocs(indexXml);
  const pageUrls = indexLocs.filter(u => /sitemap\.xml(\?|$)/.test(u));
  // If the root file is itself a urlset (no nested index), treat it as one page.
  const pages = pageUrls.length ? pageUrls.slice(0, maxSitemapPages) : [indexUrl];
  console.error(`  sitemap index has ${pageUrls.length} pages (cap ${maxSitemapPages}) — walking ${pages.length}`);
  const allUrls = new Set();
  for (let i = 0; i < pages.length; i++) {
    const url = pages[i];
    let xml;
    try {
      xml = await fetchHtml(url, { timeoutMs: 60000, retries: 3 });
    } catch (e) {
      console.error(`  [page ${i + 1}/${pages.length}] fetch failed: ${e.message} — skipping`);
      continue;
    }
    const locs = extractSitemapLocs(xml).filter(u => !/sitemap\.xml(\?|$)/.test(u));
    let added = 0;
    for (const u of locs) { if (!allUrls.has(u)) { allUrls.add(u); added++; } }
    console.error(`  [page ${i + 1}/${pages.length}] ${locs.length} locs (${added} new) — running total ${allUrls.size}`);
    if (rateMs > 0 && i < pages.length - 1) await sleep(rateMs);
  }
  return [...allUrls];
}

function isSponsoredUrl(url) {
  return /\/[^/]+\/sponsored-articles\//.test(url);
}

function urlPathSegments(url) {
  try {
    const u = new URL(url);
    return u.pathname.split('/').filter(Boolean);
  } catch {
    return [];
  }
}

function urlSlug(url) {
  const segs = urlPathSegments(url);
  return (segs[segs.length - 1] || '').toLowerCase();
}

function urlTypeSegment(url) {
  const segs = urlPathSegments(url);
  return (segs.length >= 3 ? segs[1] : '').toLowerCase();
}

function urlSectorSegment(url) {
  const segs = urlPathSegments(url);
  return (segs[0] || '').toLowerCase();
}

function buildSlugKeywordMatchers(keywords) {
  // 1:1 — each keyword maps to exactly one kebab-cased slug matcher. We do NOT
  // split multi-word keywords into bare tokens. That used to expand "DBS Bank"
  // into ["dbs-bank", "dbs", "bank"], and "bank" matched every banking-section
  // slug on SBR — silently inflating fetch volume by ~6×. The fix pushes that
  // judgment up to the keyword-proposal step in SKILL.md: if you want a slug
  // like `vickers-asia-rebrand` (no parent prefix) to match, list "Vickers" as
  // its own keyword. Predictable behaviour, no surprises.
  const out = new Set();
  for (const k of keywords) {
    const kebab = k.toLowerCase().trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
    if (kebab.length >= 2) out.add(kebab);
  }
  return [...out];
}

function slugMatchesKeyword(slug, slugMatchers) {
  return slugMatchers.some(m => slug.includes(m));
}

function extractCanonical(html) {
  const m = html.match(/<link\s+rel=["']canonical["']\s+href=["']([^"']+)["']/i);
  return m ? m[1] : null;
}

function extractJsonLd(html) {
  const blocks = [...html.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/g)];
  for (const b of blocks) {
    try {
      const parsed = JSON.parse(b[1]);
      const candidates = parsed['@graph'] ? parsed['@graph'] : [parsed];
      const article = candidates.find((x) => {
        const t = x['@type'];
        if (Array.isArray(t)) return t.some(y => /Article/.test(y));
        return /Article/.test(String(t || ''));
      });
      if (article) return article;
    } catch {/* ignore malformed block */ }
  }
  return null;
}

function extractTitle(html, jsonLd, titleSuffixRe) {
  if (jsonLd?.headline) return decodeEntities(String(jsonLd.headline)).trim();
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (!m) return null;
  return decodeEntities(m[1].replace(titleSuffixRe, '').trim());
}

function extractBodyText(html, maxChars) {
  let s = html;
  s = s.replace(/<head[\s\S]*?<\/head>/i, '');
  s = s.replace(/<script[\s\S]*?<\/script>/g, ' ');
  s = s.replace(/<style[\s\S]*?<\/style>/g, ' ');
  s = s.replace(/<header[\s\S]*?<\/header>/gi, ' ');
  s = s.replace(/<footer[\s\S]*?<\/footer>/gi, ' ');
  s = s.replace(/<nav[\s\S]*?<\/nav>/gi, ' ');
  s = s.replace(/<aside[\s\S]*?<\/aside>/gi, ' ');
  const mainMatch = s.match(/<main[\s\S]*?<\/main>/i);
  const target = mainMatch ? mainMatch[0] : s;
  const text = target.replace(/<[^>]+>/g, ' ');
  return decodeEntities(text).replace(/\s+/g, ' ').trim().slice(0, maxChars * 4);
}

function passesKeywordFilter(title, bodyHead, keywords) {
  const haystack = `${title || ''} ${bodyHead || ''}`.toLowerCase();
  return keywords.some(k => haystack.includes(k.toLowerCase()));
}

function dateOnly(iso) {
  if (!iso) return null;
  const m = String(iso).match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

function mapCategoryFromUrl(url) {
  const t = urlTypeSegment(url);
  if (URL_TYPE_TO_TAXON[t]) return URL_TYPE_TO_TAXON[t];
  // First-segment fallback for non-sectoral type containers like /exclusives/<slug>.
  const s = urlSectorSegment(url);
  if (s === 'exclusives' || s === 'exclusive') return 'Exclusives';
  return 'Sectors';
}

async function processArticle(url, opts, { timeoutMs = 45000, retries = 2 } = {}) {
  const { maxBodyChars, titleSuffixRe } = opts;
  try {
    const html = await fetchHtml(url, { timeoutMs, retries });
    const canonical = extractCanonical(html) || url;
    const jsonLd = extractJsonLd(html);
    const title = extractTitle(html, jsonLd, titleSuffixRe);
    const body = extractBodyText(html, maxBodyChars);
    const bodyHead = body.slice(0, maxBodyChars);
    return {
      ok: true,
      sourceUrl: url,
      url: canonical,
      title,
      datePublished: jsonLd?.datePublished || jsonLd?.dateCreated || null,
      rawCategory: jsonLd?.articleSection ?? null,
      bodyHead,
    };
  } catch (e) {
    return { ok: false, sourceUrl: url, error: e.message };
  }
}

async function fetchArticlesParallel(urls, opts) {
  const { concurrency } = opts;
  const results = new Array(urls.length);
  let cursor = 0;
  let done = 0;
  async function worker() {
    while (cursor < urls.length) {
      const i = cursor++;
      results[i] = await processArticle(urls[i], opts);
      done++;
      if (done % 25 === 0 || done === urls.length) {
        console.error(`  fetched ${done}/${urls.length}`);
      }
    }
  }
  const workers = Array.from({ length: Math.max(1, concurrency) }, worker);
  await Promise.all(workers);
  return results;
}

async function main() {
  const args = parseArgs(process.argv);
  const site = SITES[args.site];
  args.titleSuffixRe = site.titleSuffixRe;
  const cacheDir = resolve(args.outputDir, args.site, '.cache');
  await mkdir(cacheDir, { recursive: true });
  const slug = slugify(args.brand);

  console.error(`\n[1/4] Walking sitemap on ${site.domain} (${site.publication}) ...`);
  const allUrls = await walkSitemap(site.domain, args);
  console.error(`  -> ${allUrls.length} unique URLs from sitemap`);

  console.error(`\n[2/4] URL pre-filter (drop sponsored, keep slug-keyword matches) ...`);
  const slugMatchers = buildSlugKeywordMatchers(args.keywordList);
  console.error(`  slug matchers (1:1 with keywords): ${slugMatchers.join(', ')}`);
  const sponsoredUrls = [];
  const nonSponsored = [];
  for (const u of allUrls) {
    if (isSponsoredUrl(u)) sponsoredUrls.push(u);
    else nonSponsored.push(u);
  }
  const slugMatched = nonSponsored.filter(u => slugMatchesKeyword(urlSlug(u), slugMatchers));
  const slugMissed = nonSponsored.filter(u => !slugMatchesKeyword(urlSlug(u), slugMatchers));
  console.error(`  sponsored dropped: ${sponsoredUrls.length}`);
  console.error(`  slug-keyword matched: ${slugMatched.length} (out of ${nonSponsored.length} non-sponsored)`);

  console.error(`\n[3/4] Fetching ${slugMatched.length} article pages (concurrency ${args.concurrency}) ...`);
  const fetched = await fetchArticlesParallel(slugMatched, args);
  const firstPassFailed = fetched.map((r, i) => ({ r, i })).filter(x => !x.r.ok);
  if (firstPassFailed.length) {
    console.error(`  ${firstPassFailed.length} first-pass failures — retrying sequentially with longer timeout`);
    for (const { r, i } of firstPassFailed) {
      const retried = await processArticle(r.sourceUrl, args, { timeoutMs: 90000, retries: 3 });
      fetched[i] = retried;
      if (retried.ok) console.error(`  recovered: ${(retried.title || retried.sourceUrl).slice(0, 70)}`);
    }
  }
  const failed = fetched.filter(r => !r.ok);
  if (failed.length) console.error(`  ${failed.length} final fetch failures (logged in raw output)`);

  console.error(`\n[4/4] Title+body keyword filter: ${args.keywordList.join(', ')}`);
  const enriched = fetched.map(r => {
    if (!r.ok) {
      return { ...r, kept: false, dropReason: `fetch_failed: ${r.error}` };
    }
    const kept = passesKeywordFilter(r.title, r.bodyHead, args.keywordList);
    const finalUrl = r.url || r.sourceUrl;
    return {
      ...r,
      url: finalUrl,
      date: dateOnly(r.datePublished),
      category: mapCategoryFromUrl(finalUrl),
      sector: urlSectorSegment(finalUrl),
      kept,
      dropReason: kept ? null : 'no_brand_keyword_in_title_or_body_head',
    };
  });

  const filtered = enriched
    .filter(r => r.kept)
    .map(r => ({
      date: r.date,
      title: r.title,
      url: r.url,
      category: r.category,
      sector: r.sector,
      rawCategory: r.rawCategory,
    }))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const rawPath = join(cacheDir, `${slug}-raw.json`);
  const filteredPath = join(cacheDir, `${slug}-filtered.json`);
  await writeFile(rawPath, JSON.stringify({
    site: args.site,
    domain: site.domain,
    publication: site.publication,
    brand: args.brand,
    keywords: args.keywordList,
    sitemapUrls: allUrls.length,
    sponsoredDropped: sponsoredUrls.length,
    slugMatched: slugMatched.length,
    fetchedAt: new Date().toISOString(),
    articles: enriched.map(r => ({
      date: r.date || null,
      title: r.title || null,
      url: r.url || r.sourceUrl,
      category: r.category || null,
      sector: r.sector || null,
      rawCategory: r.rawCategory ?? null,
      kept: !!r.kept,
      dropReason: r.dropReason || null,
      bodyHead: r.bodyHead ? r.bodyHead.slice(0, 350) : null,
    })),
    sponsoredUrls,
    slugMissedCount: slugMissed.length,
  }, null, 2));
  await writeFile(filteredPath, JSON.stringify({
    site: args.site,
    domain: site.domain,
    publication: site.publication,
    brand: args.brand,
    keywords: args.keywordList,
    fetchedAt: new Date().toISOString(),
    totalKept: filtered.length,
    articles: filtered,
  }, null, 2));

  const kept = enriched.filter(r => r.kept).length;
  const dropped = enriched.length - kept;
  console.error(`\nSummary:`);
  console.error(`  Site:              ${args.site} (${site.domain} — ${site.publication})`);
  console.error(`  Sitemap URLs:      ${allUrls.length}`);
  console.error(`  Sponsored dropped: ${sponsoredUrls.length}`);
  console.error(`  Slug-matched:      ${slugMatched.length}`);
  console.error(`  Fetched:           ${slugMatched.length - failed.length} ok, ${failed.length} failed`);
  console.error(`  Kept (final):      ${kept}`);
  console.error(`  Dropped (filter):  ${dropped - failed.length}`);
  console.error(`  Raw output:        ${rawPath}`);
  console.error(`  Filtered output:   ${filteredPath}`);
}

main().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
