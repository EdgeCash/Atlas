"""For games in windows.jsonl: the 1-min tape from FT-10min to expiry+3min; winner display ask inside the real window."""
import json, time, urllib.request, gzip, sys, datetime as dt, os
IN, OUT = sys.argv[1], sys.argv[2]; GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5
G = "https://gateway.polymarket.us"
done = set(json.loads(l)["slug"] for l in open(OUT)) if os.path.exists(OUT) else set()
f = open(OUT, "a")
for l in open(IN):
    r = json.loads(l)
    if r["slug"] in done or not r.get("fin") or not (r.get("lps") or {}).get("ts"): continue
    fin = dt.datetime.fromisoformat(r["fin"].replace("Z", "+00:00")); exp = dt.datetime.fromisoformat(r["lps"]["ts"][:26].rstrip("Z") + "+00:00")
    if not (-60 < (exp - fin).total_seconds() < 180 * 60): continue
    s, e = int(fin.timestamp()) - 600, int(exp.timestamp()) + 180
    time.sleep(GAP)
    try:
        req = urllib.request.Request(G + f"/v1/price-history?symbol={r['ml']}&timestamp.startTimestamp={s}&timestamp.endTimestamp={e}&fidelity=1", headers={"Accept-Encoding": "gzip", "User-Agent": "research-readonly"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            b = resp.read(); b = gzip.decompress(b) if resp.headers.get("Content-Encoding") == "gzip" else b
        h = json.loads(b).get("history", [])
    except Exception as ex:
        continue
    r["tape"] = [(x.get("timestamp"), x.get("longPrice"), x.get("shortPrice")) for x in h]
    f.write(json.dumps(r) + "\n"); f.flush()
print("done")
