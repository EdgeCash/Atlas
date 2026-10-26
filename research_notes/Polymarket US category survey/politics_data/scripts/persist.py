import sys,json,time,urllib.request; sys.path.insert(0,sys.argv[1]); from g import get
G=json.load(open("../raw/xv_gamma.json"))
def tok(ev,gslug,name):
    for c in G[ev]["cands"]:
        if c["slug"]!=gslug: continue
        for m in c["markets"]:
            if (m["git"] or m["q"]).startswith(name): return json.loads(m["tok"])[0]
pairs=[("usgcc-aliens-12-31-2026","aliens","will-the-us-confirm-that-aliens-exist-before-2027","December 31"),
("opdc-trump-resig-2026-12-31","trump-resig","will-trump-resign-by-december-31-2026","Will Trump resign"),
("mowc-nato-us-12-31-2026","nato-us","will-us-withdraw-from-nato-before-2027","December 31"),
("enwc-uspres-nom-dem-2028-gavnew","uspres-nom-dem-2028","democratic-presidential-nominee-2028","Gavin Newsom"),
("enwc-uspres-nom-dem-2028-aleocc","uspres-nom-dem-2028","democratic-presidential-nominee-2028","Alexandria"),
("pintc-meet-trump-2026-12-31-vlaput","meet-trump-2026-12-31","who-will-trump-meet-with-in-2026","Vladimir Putin"),
("dipcc-us-iran-contnts-2026--enrmor","us-iran-contnts-2026-","what-will-be-in-a-us-iran-deal-in-2026-20260624150226501","1+ Year"),
("opdc-zelenskyy-presuk-2027-06-30","zelenskyy-presuk","zelenskyy-out-as-ukraine-president-by-june-30-2027","Zelenskyy"),
("ewc-usp-2028-11-07-jdvan","usp-2028-11-07","presidential-election-winner-2028","JD Vance"),
("apdc-petehegseth-2026-12-31","petehegseth","pete-hegseth-out-as-secretary-of-defense-by-december-31","Pete"),
("stsc-hormuz-normal-2026-12-31","hormuz-normal","strait-of-hormuz-traffic-returns-to-normal-by-december-31","Strait"),
("ewc-usp-party-2028-11-07-dem","usp-party-2028-11-07","presidential-election-winner-2028","Gavin Newsom"),
]
out={}
for pm,ev,gs,name in pairs:
    t=tok(ev,gs,name)
    if not t: print("no token",pm); continue
    h=get("https://gateway.polymarket.us/v1/price-history",{"symbol":pm,"fixedInterval":"INTERVAL_ALL","fidelity":60})
    p=[(int(x["timestamp"]),float(x.get("longPrice") or 0)) for x in (h or {}).get("history",[])]
    u=f"https://clob.polymarket.com/prices-history?market={t}&interval=max&fidelity=60"
    try: gh=json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"research"}),timeout=60).read()).get("history",[])
    except Exception as e: gh=[]; print("err",e)
    out[pm]={"pm":p,"g":[(x["t"],x["p"]) for x in gh],"gname":name}
    print(pm,len(p),len(gh),flush=True); time.sleep(0.5)
json.dump(out,open("../raw/persist.json","w"))
