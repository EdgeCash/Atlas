import json, sys, time, urllib.request, os, datetime as dt
rows = json.load(open(sys.argv[1])); outdir = sys.argv[2]; since = sys.argv[3]
os.makedirs(outdir, exist_ok=True)
for r in rows:
    if not r['slug'].startswith('tc-temp-'): continue
    D = r['event'][-10:]
    if D < since: continue
    fn = f"{outdir}/{r['slug']}.json"
    if os.path.exists(fn): continue
    d0 = dt.datetime.fromisoformat(D + "T14:00:00+00:00")
    s, e = int(d0.timestamp()), int((d0 + dt.timedelta(hours=19)).timestamp())
    url = f"https://gateway.polymarket.us/v1/price-history?symbol={r['slug']}&timestamp.startTimestamp={s}&timestamp.endTimestamp={e}&fidelity=1"
    d = None
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp: d = json.load(resp); break
        except urllib.error.HTTPError as ex:
            if ex.code == 429: time.sleep(2 ** i + 1); continue
            d = {"err": ex.code}; break
        except Exception as ex:
            time.sleep(2); d = {"err": str(ex)}
    h = (d or {}).get("history") or []
    json.dump({"start": s, "end": e, "h": [[x["timestamp"], x.get("longPrice"), x.get("shortPrice")] for x in h], "err": (d or {}).get("err")}, open(fn, "w"))
    time.sleep(1.8)
print("done")
