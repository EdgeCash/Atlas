import sys,json; sys.path.insert(0,sys.argv[1]); from g import get
legs=[]
for e in json.load(open("../raw/nonmid_open.json")):
    for m in e["markets"]:
        if m["status"]!="MARKET_STATUS_OPEN": legs.append((e["slug"],m["slug"],m.get("title"),m.get("endDate"),m.get("description","")[:300]))
for e in json.load(open("../raw/closed_politics.json")):
    if e["slug"].split("-")[0] in ("ushrp","ussep","usgubp","ushr","usse","usgub","uss","ush","usmayor"): continue
    for m in e["markets"]: legs.append((e["slug"],m["slug"],m.get("title"),m.get("endDate"),m.get("description","")[:300]))
out=[]
for ev,s,t,end,desc in legs:
    st=get(f"https://gateway.polymarket.us/v1/markets/{s}/settlement")
    h=get("https://gateway.polymarket.us/v1/price-history",{"symbol":s,"fixedInterval":"INTERVAL_ALL","fidelity":60})
    hist=[(int(x["timestamp"]),float(x.get("longPrice") or 0)) for x in (h or {}).get("history",[])]
    out.append({"ev":ev,"slug":s,"title":t,"end":end,"desc":desc,"settle":(st or {}).get("settlement"),"hist":hist})
    print(ev,s,t,(st or {}).get("settlement"),len(hist),flush=True)
json.dump(out,open("../raw/resolved_legs.json","w"))
