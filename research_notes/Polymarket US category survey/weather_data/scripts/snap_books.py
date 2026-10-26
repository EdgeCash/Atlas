import json, sys, time, urllib.request, datetime
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src))
res = {"ts": datetime.datetime.utcnow().isoformat()+"Z", "books": {}}
def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(url, timeout=20) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(2**i); continue
            return {"err": e.code}
        except Exception as e:
            time.sleep(1); err = str(e)
    return {"err": "fail"}
for e in d["events"]:
    for m in e["markets"]:
        s = m["slug"]
        res["books"][s] = {"event": e["slug"], "title": m.get("title"), "book": get(f"https://gateway.polymarket.us/v1/markets/{s}/book")}
        time.sleep(0.55)
json.dump(res, open(out, "w"))
print("done", len(res["books"]))
