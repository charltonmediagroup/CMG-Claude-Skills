#!/usr/bin/env node
// Earned Media Report — Travel Daily Media scraper + filter
//
// Pulls every article from https://www.traveldailymedia.com/?s=<brand>, fetches
// each result page, parses JSON-LD for date and category, applies a brand-keyword
// filter, and writes a JSON dataset that the companion skill turns into an HTML/PDF
// report.
//
// Usage:
//   node scripts/earned-media-report.mjs \
//     --brand "Minor Hotels" \
//     --keywords "Minor Hotels,Anantara,Avani,Tivoli,NH,Oaks,nhow,Colbert Collection,Wolseley,Elewana"
//
// Optional flags:
//   --output-dir output/earned-media   (default)
//   --rate-ms 250                      delay between search-page requests
//   --concurrency 8                    parallel article fetches
//   --max-body-chars 350               filter window into article body
//   --max-pages 50                     hard cap on search pagination

import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const BASE = 'https://www.traveldailymedia.com';

// Raw articleSection labels → report taxonomy. First matching keyword wins.
// Taxonomy order matters when an article carries multiple sections.
const CATEGORY_RULES = [
  { taxon: 'Appointments',         match: /appointment|people|movers|new\s+hire/i },
  { taxon: 'Awards',               match: /award/i },
  { taxon: 'Reports & Financials', match: /financial|results|earnings|report|finance/i },
  { taxon: 'Interviews',           match: /interview|q\s*&\s*a|face[- ]to[- ]face/i },
  { taxon: 'Partner Articles',     match: /partner|sponsored|advertorial/i },
  { taxon: 'Exclusives',           match: /exclusive/i },
  { taxon: 'Events',               match: /event/i },
  { taxon: 'Sectors',              match: /sector|technology|sustainab|trend|brand|opinion|feature/i },
  { taxon: 'Markets',              match: /./ }, // fallback
];

function parseArgs(argv) {
  const args = {
    brand: null,
    keywords: null,
    outputDir: 'output/earned-media/.cache',
    rateMs: 1500,
    concurrency: 4,
    maxBodyChars: 350,
    maxPages: 50,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case '--brand': args.brand = next(); break;
      case '--keywords': args.keywords = next(); break;
      case '--output-dir': args.outputDir = next(); break;
      case '--rate-ms': args.rateMs = Number(next()); break;
      case '--concurrency': args.concurrency = Number(next()); break;
      case '--max-body-chars': args.maxBodyChars = Number(next()); break;
      case '--max-pages': args.maxPages = Number(next()); break;
      case '-h': case '--help':
        printHelp(); process.exit(0);
      default:
        console.error(`Unknown flag: ${a}`); process.exit(2);
    }
  }
  if (!args.brand || !args.keywords) {
    console.error('--brand and --keywords are required');
    printHelp();
    process.exit(2);
  }
  args.keywordList = args.keywords.split(',').map(s => s.trim()).filter(Boolean);
  return args;
}

function printHelp() {
  console.log(`Usage:
  node scripts/earned-media-report.mjs --brand "Minor Hotels" --keywords "Minor Hotels,Anantara,..."

Required:
  --brand        Brand name (used in TDM site search and as report label)
  --keywords     Comma-separated keyword list (parent + sub-brands). An article is kept
                 only if at least one keyword appears in the title or first N chars of body.

Optional:
  --output-dir   Directory for JSON outputs (default: output/earned-media/.cache)
  --rate-ms      Delay between search-page requests (default: 1500)
  --concurrency  Parallel article fetches (default: 4)
  --max-body-chars  Body window for keyword filter (default: 350)
  --max-pages    Search pagination cap (default: 50)
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

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const backoffMs = (attempt) => Math.min(2000 * Math.pow(2, attempt), 15000); // 2s, 4s, 8s, 15s cap

function extractSearchHits(html) {
  const re = /<h2 class="overflow_line_2">\s*<a href="([^"]+)">([\s\S]*?)<\/a>\s*<\/h2>/g;
  const out = [];
  let m;
  while ((m = re.exec(html)) !== null) {
    const url = m[1].trim();
    const title = decodeEntities(m[2].replace(/\s+/g, ' ').trim());
    out.push({ url, title });
  }
  return out;
}

async function paginateSearch(brand, { rateMs, maxPages }) {
  const encoded = encodeURIComponent(brand).replace(/%20/g, '+');
  const seen = new Set();
  const all = [];
  let pagesScanned = 0;
  for (let page = 1; page <= maxPages; page++) {
    const url = page === 1
      ? `${BASE}/?s=${encoded}`
      : `${BASE}/page/${page}/?s=${encoded}`;
    let html;
    try {
      html = await fetchHtml(url, { timeoutMs: 60000, retries: 3 });
    } catch (e) {
      // After multiple retries failed, the page is either past the end or TDM is hard-throttling.
      // If we have at least one earlier successful page, treat as end-of-results.
      console.error(`  [page ${page}] fetch failed after retries: ${e.message}; treating as end of results`);
      break;
    }
    const hits = extractSearchHits(html);
    pagesScanned = page;
    if (hits.length === 0) {
      console.error(`  [page ${page}] empty — stopping`);
      break;
    }
    let newCount = 0;
    for (const h of hits) {
      if (!seen.has(h.url)) {
        seen.add(h.url);
        all.push(h);
        newCount++;
      }
    }
    console.error(`  [page ${page}] ${hits.length} hits (${newCount} new) — running total ${all.length}`);
    // If no new URLs on this page, the rest is just sticky duplicates → stop.
    if (newCount === 0) {
      console.error(`  [page ${page}] no new URLs — stopping`);
      break;
    }
    if (rateMs > 0) await sleep(rateMs);
  }
  return { articles: all, pagesScanned };
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

function extractTitle(html, jsonLd) {
  if (jsonLd?.headline) return decodeEntities(String(jsonLd.headline)).trim();
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (!m) return null;
  // TDM titles end with " - Travel Daily Media" or similar
  return decodeEntities(m[1].replace(/\s*[-|–]\s*Travel\s*Daily\s*Media.*$/i, '').trim());
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
  return decodeEntities(text).replace(/\s+/g, ' ').trim().slice(0, maxChars * 4); // grab a bit more so caller can trim cleanly
}

function mapCategory(rawSection) {
  if (!rawSection) return 'Markets';
  const sections = Array.isArray(rawSection) ? rawSection : [rawSection];
  const blob = sections.join(' | ');
  for (const rule of CATEGORY_RULES) {
    if (rule.match.test(blob)) return rule.taxon;
  }
  return 'Markets';
}

function passesKeywordFilter(title, bodyHead, keywords) {
  const haystack = `${title || ''} ${bodyHead || ''}`.toLowerCase();
  return keywords.some(k => haystack.includes(k.toLowerCase()));
}

async function processArticle(hit, opts, { timeoutMs = 45000, retries = 2 } = {}) {
  const { maxBodyChars } = opts;
  try {
    const html = await fetchHtml(hit.url, { timeoutMs, retries });
    const canonical = extractCanonical(html) || hit.url;
    const jsonLd = extractJsonLd(html);
    const title = extractTitle(html, jsonLd) || hit.title;
    const body = extractBodyText(html, maxBodyChars);
    const bodyHead = body.slice(0, maxBodyChars);
    return {
      ok: true,
      searchUrl: hit.url,
      url: canonical,
      title,
      datePublished: jsonLd?.datePublished || null,
      rawCategory: jsonLd?.articleSection ?? null,
      bodyHead,
    };
  } catch (e) {
    return { ok: false, searchUrl: hit.url, title: hit.title, error: e.message };
  }
}

async function fetchArticlesParallel(hits, opts) {
  const { concurrency } = opts;
  const results = new Array(hits.length);
  let cursor = 0;
  let done = 0;
  async function worker() {
    while (cursor < hits.length) {
      const i = cursor++;
      results[i] = await processArticle(hits[i], opts);
      done++;
      if (done % 10 === 0 || done === hits.length) {
        console.error(`  fetched ${done}/${hits.length}`);
      }
    }
  }
  const workers = Array.from({ length: Math.max(1, concurrency) }, worker);
  await Promise.all(workers);
  return results;
}

function dateOnly(iso) {
  if (!iso) return null;
  const m = String(iso).match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

async function main() {
  const args = parseArgs(process.argv);
  const outputDir = resolve(args.outputDir);
  await mkdir(outputDir, { recursive: true });
  const slug = slugify(args.brand);

  console.error(`\n[1/3] Searching TDM for "${args.brand}" ...`);
  const { articles: hits, pagesScanned } = await paginateSearch(args.brand, args);
  console.error(`  -> ${hits.length} unique URLs across ${pagesScanned} page(s)`);

  console.error(`\n[2/3] Fetching ${hits.length} article pages (concurrency ${args.concurrency}) ...`);
  const fetched = await fetchArticlesParallel(hits, args);
  const firstPassFailed = fetched.map((r, i) => ({ r, i })).filter(x => !x.r.ok);
  if (firstPassFailed.length) {
    console.error(`  ${firstPassFailed.length} first-pass failures — retrying sequentially with longer timeout`);
    for (const { r, i } of firstPassFailed) {
      const retried = await processArticle({ url: r.searchUrl, title: r.title }, args, { timeoutMs: 90000, retries: 3 });
      fetched[i] = retried;
      if (retried.ok) console.error(`  recovered: ${retried.title?.slice(0, 70)}`);
    }
  }
  const failed = fetched.filter(r => !r.ok);
  if (failed.length) console.error(`  ${failed.length} final fetch failures (logged in raw output)`);

  console.error(`\n[3/3] Filtering by brand keywords: ${args.keywordList.join(', ')}`);
  const enriched = fetched.map(r => {
    if (!r.ok) {
      return { ...r, kept: false, dropReason: `fetch_failed: ${r.error}` };
    }
    const kept = passesKeywordFilter(r.title, r.bodyHead, args.keywordList);
    return {
      ...r,
      date: dateOnly(r.datePublished),
      category: mapCategory(r.rawCategory),
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
      rawCategory: r.rawCategory,
    }))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const rawPath = join(outputDir, `${slug}-raw.json`);
  const filteredPath = join(outputDir, `${slug}-filtered.json`);
  await writeFile(rawPath, JSON.stringify({
    brand: args.brand,
    keywords: args.keywordList,
    pagesScanned,
    fetchedAt: new Date().toISOString(),
    articles: enriched.map(r => ({
      date: r.date || null,
      title: r.title,
      url: r.url || r.searchUrl,
      category: r.category || null,
      rawCategory: r.rawCategory ?? null,
      kept: !!r.kept,
      dropReason: r.dropReason || null,
      bodyHead: r.bodyHead ? r.bodyHead.slice(0, 350) : null,
    })),
  }, null, 2));
  await writeFile(filteredPath, JSON.stringify({
    brand: args.brand,
    keywords: args.keywordList,
    fetchedAt: new Date().toISOString(),
    totalKept: filtered.length,
    articles: filtered,
  }, null, 2));

  const kept = enriched.filter(r => r.kept).length;
  const dropped = enriched.length - kept;
  console.error(`\nSummary:`);
  console.error(`  Pages scanned:   ${pagesScanned}`);
  console.error(`  Unique URLs:     ${hits.length}`);
  console.error(`  Kept:            ${kept}`);
  console.error(`  Dropped:         ${dropped}`);
  console.error(`  Raw output:      ${rawPath}`);
  console.error(`  Filtered output: ${filteredPath}`);
}

main().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
