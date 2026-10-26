"""Read-only: closed tennis/table-tennis events (sampled days) + kick-off price history for a sample."""
import json, time, sys, os, random, urllib.request, urllib.error, gzip, datetime as dt
OUT = sys.argv[1]; GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
os.makedirs(OUT, exist_ok=True)
G = "https://gateway.polymarket.us"
last = [0.0]
def get(path):
    for attempt in range(4):
        gap = time.time() - last[0]
        if gap < GAP: time.sleep(GAP - gap)
        last[0] = time.time()
        req = urllib.request.Request(G + path, headers={"User-Agent": "research-readonly", "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
                return json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(5 * (attempt + 1)); continue
            return None
        except Exception:
            time.sleep(2); continue
    return None
def slim(e):
    ml = [m for m in e.get("markets", []) if m.get("marketType") == "moneyline" or str(m.get("sportsMarketType", "")).endswith("winner")]
    if not ml: return None
    m = ml[0]
    return {"slug": e["slug"], "series": e.get("seriesSlug"), "start": e.get("startTime") or e.get("startDate"),
            "fin": e.get("finishedTimestamp"), "ml": m["slug"], "fee": m.get("feeCoefficient"),
            "sides": [(s.get("description"), s.get("price"), s.get("long")) for s in m.get("marketSides", [])]}
lst = os.path.join(OUT, "events.jsonl")
if not os.path.exists(lst):
    days = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(0, 116, 3)]
    with open(lst, "w") as f:
        for d in days:
            for tag, pages in (("atp", 1), ("wta", 1), ("itf", 2), ("table-tennis", 2)):
                for p in range(pages):
                    q = f"/v1/events?closed=true&limit=500&offset={500*p}&tagSlug={tag}&startDateMin={d}T00:00:00Z&startDateMax={d + dt.timedelta(days=1)}T00:00:00Z"
                    data = get(q); evs = (data or {}).get("events", [])
                    for e in evs:
                        s = slim(e)
                        if s: s["tag"] = tag; s["day"] = str(d); f.write(json.dumps(s) + "\n")
                    f.flush()
                    print(d, tag, p, len(evs), flush=True)
                    if len(evs) < 500: break
rows = {}
for l in open(lst):
    r = json.loads(l); rows[r["ml"]] = r
rows = list(rows.values()); random.seed(7); random.shuffle(rows)
quota = {"atp": 900, "wta": 500, "itf": 1000, "table-tennis": 1200}
done = set()
hp = os.path.join(OUT, "hist.jsonl")
if os.path.exists(hp):
    for l in open(hp): done.add(json.loads(l)["ml"])
cnt = {k: 0 for k in quota}
for r in rows:
    if r["ml"] in done: cnt[r["tag"]] += 1
with open(hp, "a") as f:
    for r in rows:
        if r["ml"] in done or cnt[r["tag"]] >= quota[r["tag"]]: continue
        try:
            st = int(dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")).timestamp())
        except Exception: continue
        h = get(f"/v1/price-history?symbol={r['ml']}&timestamp.startTimestamp={st-1800}&timestamp.endTimestamp={st+300}&fidelity=1")
        if h is None: continue
        r["hist"] = [(x.get("timestamp"), x.get("longPrice"), x.get("shortPrice")) for x in h.get("history", [])]
        f.write(json.dumps(r) + "\n"); f.flush(); cnt[r["tag"]] += 1
        if sum(cnt.values()) % 100 == 0: print(cnt, flush=True)
print("done", cnt)
