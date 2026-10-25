import sys, json, time, urllib.request; sys.path.insert(0,sys.argv[1]); from g import get
TSE="https://resultados.tse.jus.br/oficial/ele2026/6258/dados-simplificados/br/br-c0001-e006258-r.json"
mk=["ewc-pres-bra-2026-10-04-luisil","ewc-pres-bra-2026-10-04-flabol","vmc-presmov-bra-2026-10-25-r2-lulagte12","vmc-presmov-bra-2026-10-25-r2-lula0-4","vmc-presmov-bra-2026-10-25-r2-bols0-4"]
out=open("../raw/bra_live.jsonl","a")
end=time.time()+float(sys.argv[2])
while time.time()<end:
    rec={"t":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    try:
        req=urllib.request.Request(TSE,headers={"User-Agent":"Mozilla/5.0","Cache-Control":"no-cache"})
        d=json.loads(urllib.request.urlopen(req,timeout=30).read())
        rec["tse"]={"hg":d.get("hg"),"dg":d.get("dg"),"pst":d.get("pst"),"cand":[(c.get("nm"),c.get("pvap"),c.get("e")) for c in d.get("cand",[])], "md":d.get("md")}
    except Exception as e: rec["tse_err"]=str(e)[:100]
    for s in mk:
        b=(get(f"https://gateway.polymarket.us/v1/markets/{s}/bbo",minint=1.0) or {}).get("marketData") or {}
        rec[s]=[(b.get("bestBid") or {}).get("value"),(b.get("bestAsk") or {}).get("value"),b.get("bidShares"),b.get("askShares"),(b.get("lastPriceSample") or {}).get("ts"),b.get("state")]
    out.write(json.dumps(rec)+"\n"); out.flush()
    time.sleep(50)
