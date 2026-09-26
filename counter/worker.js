// Atlas's reader counter: a Cloudflare Worker that keeps daily counts and
// nothing else (docs/ANALYTICS_SPEC_FINAL.md, "the first-party counter").
//
//   POST /hit     the site's beacon (atlas/site/assets/readers.js)
//   GET  /counts  the counts since a day, for the owner page; needs READ_TOKEN
//
// What is kept: one row per (day, event, path, source, detail) and how many
// times it happened. What is not: the IP address, the user agent, the full
// referrer, a cookie, or anything that joins one request to another. The
// Worker sees the IP and the user agent, as every server does; it reads the
// user agent only to drop crawlers, and writes neither.
//
// Anyone can post a hit, so the counts can be inflated by someone who wants
// to. They are for reading trends, not for billing anyone.

const EVENTS = new Set(["view", "visit", "panel"]);
const VISITS = new Set(["new", "return"]);
const PATH = /^[a-z0-9][a-z0-9/._-]{0,119}$|^$/;
const NAME = /^[a-z0-9-]{1,40}$/;
const BOT = /bot|crawl|spider|slurp|bing|duckduck|yandex|baidu|facebookexternalhit|headless|curl|wget|python-requests|monitor|uptime|lighthouse/i;

// Where a visit came from, by the referrer's host. Only the label is kept.
// The same list as atlas/ops/analytics.py SOURCES.
const SOURCES = [
  ["x", ["t.co", "twitter.com", "x.com"]],
  ["threads", ["threads.net", "threads.com"]],
  ["instagram", ["instagram.com", "l.instagram.com"]],
  ["reddit", ["reddit.com", "out.reddit.com"]],
  ["search", ["google.", "bing.com", "duckduckgo.com", "search.yahoo"]],
  ["email", ["mail.google", "outlook.", "list-manage"]],
];

export function source(host, siteHosts) {
  host = String(host || "").toLowerCase();
  if (!host) return "direct";
  if (siteHosts.includes(host)) return "internal";
  for (const [label, needles] of SOURCES) {
    if (needles.some((n) => host.includes(n))) return label;
  }
  return "other";
}

// The reader's day, in Eastern time, as the rest of Atlas keeps it.
export function day(now) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(now);
}

// A beacon's body to the one row it counts, or null when it is not one.
export function row(hit, siteHosts, now) {
  if (!hit || typeof hit !== "object" || !EVENTS.has(hit.e)) return null;
  const path = typeof hit.p === "string" ? hit.p : "";
  if (!PATH.test(path) || path.includes("..")) return null;
  const r = { day: day(now), event: hit.e, path: "", source: "", detail: "" };
  if (hit.e === "view") {
    r.path = path;
    r.source = source(hit.r, siteHosts);
  } else if (hit.e === "visit") {
    if (!VISITS.has(hit.k)) return null;
    r.detail = hit.k;
  } else {
    if (!NAME.test(String(hit.n || ""))) return null;
    r.path = path;
    r.detail = hit.n;
  }
  return r;
}

function list(value) {
  return String(value || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
}

function cors(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

// Compared in constant time, so the token cannot be guessed a byte at a time.
function same(a, b) {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

async function hit(request, env) {
  const origin = request.headers.get("Origin") || "";
  const origins = list(env.ALLOWED_ORIGINS);
  if (!origins.includes(origin.toLowerCase())) return new Response(null, { status: 403 });
  const headers = cors(origin);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (BOT.test(request.headers.get("User-Agent") || "")) return new Response(null, { status: 204, headers });
  const text = await request.text();
  if (text.length > 1024) return new Response(null, { status: 413, headers });
  let body;
  try { body = JSON.parse(text); } catch { return new Response(null, { status: 400, headers }); }
  const siteHosts = origins.map((o) => { try { return new URL(o).hostname; } catch { return ""; } });
  const r = row(body, siteHosts, new Date());
  if (!r) return new Response(null, { status: 400, headers });
  await env.DB.prepare(
    "INSERT INTO counts (day, event, path, source, detail, n) VALUES (?, ?, ?, ?, ?, 1) " +
    "ON CONFLICT (day, event, path, source, detail) DO UPDATE SET n = n + 1",
  ).bind(r.day, r.event, r.path, r.source, r.detail).run();
  return new Response(null, { status: 204, headers });
}

async function counts(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (!env.READ_TOKEN || !same(auth, `Bearer ${env.READ_TOKEN}`)) return new Response(null, { status: 401 });
  const since = new URL(request.url).searchParams.get("since") || "2000-01-01";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(since)) return new Response(null, { status: 400 });
  const { results } = await env.DB.prepare(
    "SELECT day, event, path, source, detail, n FROM counts WHERE day >= ? ORDER BY day, event, path",
  ).bind(since).all();
  return Response.json({ rows: results });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === "/hit" && (request.method === "POST" || request.method === "OPTIONS")) return hit(request, env);
    if (pathname === "/counts" && request.method === "GET") return counts(request, env);
    return new Response(null, { status: 404 });
  },
};
