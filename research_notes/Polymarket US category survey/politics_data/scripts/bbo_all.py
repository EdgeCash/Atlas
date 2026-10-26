import sys, json, time; sys.path.insert(0,sys.argv[1]); from g import get
sel=json.load(open("../raw/nonmid_open.json"))
out={}
for e in sel:
    for m in e["markets"]:
        if m["status"]!="MARKET_STATUS_OPEN": continue
        d=get(f"https://gateway.polymarket.us/v1/markets/{m['slug']}/bbo")
        out[m["slug"]]={"event":e["slug"],"title":m.get("title"),"t":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"bbo":(d or {}).get("marketData")}
json.dump(out,open("../raw/bbo_nonmid.json","w"))
print(len(out))
