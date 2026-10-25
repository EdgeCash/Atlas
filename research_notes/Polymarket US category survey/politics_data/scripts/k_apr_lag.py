import sys,json,datetime as dt; sys.path.insert(0,sys.argv[1]); from k import kget
evs=json.load(open("../raw/k_apr_events.json"))
weekly=[e["event_ticker"] for e in evs if e["event_ticker"]!="KXAPRPOTUS-26OCT30"][:26]
res=[]
for ev in weekly:
    d=kget("/markets",{"event_ticker":ev,"limit":50})
    if not d: continue
    ms=d["markets"]; w=[m for m in ms if m.get("result")=="yes"]
    if not w: continue
    w=w[0]; close=dt.datetime.fromisoformat(w["close_time"].replace("Z","+00:00")); ct=int(close.timestamp())
    c=kget(f"/series/KXAPRPOTUS/markets/{w['ticker']}/candlesticks",{"start_ts":ct-6*3600,"end_ts":ct,"period_interval":1})
    cs=(c or {}).get("candlesticks",[])
    rows=[(x["end_period_ts"],(x.get("yes_ask") or {}).get("close_dollars") or (x.get("yes_ask") or {}).get("close"),(x.get("yes_bid") or {}).get("close_dollars") or (x.get("yes_bid") or {}).get("close"),x.get("volume_fp",x.get("volume"))) for x in cs]
    res.append({"ev":ev,"win":w["ticker"],"sub":w["yes_sub_title"],"exp":w.get("expiration_value"),"close":ct,"vol":sum(float(m["volume_fp"]) for m in ms),"candles":rows})
    print(ev, w["yes_sub_title"], len(rows), rows[-1] if rows else None, flush=True)
json.dump(res,open("../raw/k_apr_lag.json","w"))
