import json, sys, time, urllib.request, os
rows = json.load(open(sys.argv[1])); outdir = sys.argv[2]; fid = sys.argv[3]
os.makedirs(outdir, exist_ok=True)
for r in rows:
    fn = f"{outdir}/{r['slug']}.json"
    if os.path.exists(fn): continue
    url = f"https://gateway.polymarket.us/v1/price-history?symbol={r['slug']}&fidelity={fid}&fixedInterval=INTERVAL_ALL"
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp: d = json.load(resp); break
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(2 ** i + 1); continue
            d = {"err": e.code}; break
        except Exception as e:
            time.sleep(2); d = {"err": str(e)}
    json.dump(d, open(fn, "w"))
    time.sleep(0.5)
print("done")
