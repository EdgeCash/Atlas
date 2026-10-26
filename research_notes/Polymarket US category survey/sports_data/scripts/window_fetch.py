"""Read-only: recent settled US-major games -> finishedTimestamp vs book expiry (bbo lastPriceSample.ts)."""
import json, time, urllib.request, gzip, sys
OUT = sys.argv[1]
G = "https://gateway.polymarket.us"
def get(p):
    time.sleep(2.5)
    req = urllib.request.Request(G + p, headers={"Accept-Encoding": "gzip", "User-Agent": "research-readonly"})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read(); b = gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b
                return json.loads(b)
        except Exception as e:
            time.sleep(4)
    return None
import os
done = set(json.loads(l)["slug"] for l in open(OUT)) if os.path.exists(OUT) else set()
f = open(OUT, "a")
for tag, start in (("nba", "2026-10-20"), ("nhl", "2026-10-15"), ("nfl", "2026-10-01"), ("cfb", "2026-10-10"), ("mlb", "2026-09-20"), ("cbb", "2026-03-01")):
    d = get(f"/v1/events?closed=true&limit=200&tagSlug={tag}&startDateMin={start}T00:00:00Z")
    evs = (d or {}).get("events", [])
    games = [e for e in evs if e.get("finishedTimestamp") and any(m.get("marketType") == "moneyline" for m in e.get("markets", []))]
    print(tag, len(evs), len(games), flush=True)
    for e in games[:60]:
        if e["slug"] in done: continue
        m = [m for m in e["markets"] if m.get("marketType") == "moneyline"][0]
        b = get(f"/v1/markets/{m['slug']}/bbo")
        md = (b or {}).get("marketData") or {}
        f.write(json.dumps({"tag": tag, "slug": e["slug"], "fin": e.get("finishedTimestamp"), "start": e.get("startTime"),
                            "ml": m["slug"], "tick": m.get("orderPriceMinTickSize"), "sides": [(s.get("description"), s.get("price"), s.get("long")) for s in m.get("marketSides", [])],
                            "lps": md.get("lastPriceSample"), "ltp": md.get("lastTradePx"), "settle": md.get("settlementPx"), "state": md.get("state")}) + "\n"); f.flush()
print("done")
