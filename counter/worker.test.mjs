// node --test counter/worker.test.mjs   (tests/test_readers.py runs it when node is installed)
import assert from "node:assert/strict";
import { test } from "node:test";

import worker, { day, row, source } from "./worker.js";

const SITE = ["edgecash.github.io"];
const NOON = new Date("2026-09-26T16:00:00Z");

test("a view keeps its page and only the label of where it came from", () => {
  assert.deepEqual(row({ e: "view", p: "ncaaf/iowa-michigan.html", r: "t.co" }, SITE, NOON),
    { day: "2026-09-26", event: "view", path: "ncaaf/iowa-michigan.html", source: "x", detail: "" });
  assert.equal(source("edgecash.github.io", SITE), "internal");
  assert.equal(source("www.google.com", SITE), "search");
  assert.equal(source("", SITE), "direct");
  assert.equal(source("someblog.net", SITE), "other");
});

test("the day is the reader's, in Eastern time", () => {
  assert.equal(day(new Date("2026-09-27T03:30:00Z")), "2026-09-26");
});

test("a visit is new or returning and nothing else; a panel has a plain name", () => {
  assert.equal(row({ e: "visit", k: "return" }, SITE, NOON).detail, "return");
  assert.equal(row({ e: "visit", k: "id-123" }, SITE, NOON), null);
  assert.equal(row({ e: "panel", p: "ncaaf/a.html", n: "market-detail" }, SITE, NOON).detail, "market-detail");
  assert.equal(row({ e: "panel", p: "ncaaf/a.html", n: "<b>" }, SITE, NOON), null);
});

test("anything else is refused", () => {
  for (const hit of [null, {}, { e: "click" }, { e: "view", p: "../x" }, { e: "view", p: "/abs.html" },
    { e: "view", p: "a".repeat(200) }]) {
    assert.equal(row(hit, SITE, NOON), null, JSON.stringify(hit));
  }
});

function env(rows) {
  return {
    ALLOWED_ORIGINS: "https://edgecash.github.io",
    READ_TOKEN: "t0ken",
    DB: {
      prepare: (sql) => ({
        bind: (...args) => ({
          run: async () => rows.push(args),
          all: async () => ({ results: rows.map(([d, e, p, s, x]) => ({ day: d, event: e, path: p, source: s, detail: x, n: 1 })) }),
        }),
      }),
    },
  };
}

function post(body, headers = {}) {
  return new Request("https://c.example/hit", {
    method: "POST", body,
    headers: { Origin: "https://edgecash.github.io", "User-Agent": "Mozilla/5.0 (iPhone)", ...headers },
  });
}

test("a hit is stored with no address and no user agent; other sites and crawlers are not", async () => {
  const rows = [];
  const e = env(rows);
  assert.equal((await worker.fetch(post('{"e":"visit","k":"new"}'), e)).status, 204);
  assert.equal(rows.length, 1);
  assert.equal(JSON.stringify(rows).includes("iPhone"), false);
  assert.equal((await worker.fetch(post('{"e":"visit","k":"new"}', { Origin: "https://other.example" }), e)).status, 403);
  assert.equal((await worker.fetch(post('{"e":"visit","k":"new"}', { "User-Agent": "Googlebot/2.1" }), e)).status, 204);
  assert.equal(rows.length, 1);
});

test("the counts are read only with the token", async () => {
  const e = env([["2026-09-26", "visit", "", "", "new"]]);
  const read = (auth) => worker.fetch(new Request("https://c.example/counts?since=2026-09-01",
    { headers: auth ? { Authorization: auth } : {} }), e);
  assert.equal((await read()).status, 401);
  assert.equal((await read("Bearer nope")).status, 401);
  const ok = await read("Bearer t0ken");
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).rows[0].detail, "new");
});
