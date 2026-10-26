import sys,json,datetime as dt; sys.path.insert(0,sys.argv[1]); from g import get
def ts(s): return int(dt.datetime.fromisoformat(s+"+00:00").timestamp())
W=[("nocc-dni-jayclay-2026-08-07","2026-07-28T12:00","2026-07-29T11:59"),
   ("nocc-dni-jayclay-2026-12-18","2026-07-28T12:00","2026-07-29T11:59"),
   ("nphc-attgen-todbla","2026-08-07T16:00","2026-08-08T15:59"),
   ("nocc-attgen-todblanche-2026-08-07","2026-08-07T16:00","2026-08-08T15:59"),
   ("pvwc-pres-bra-2026-10-04-r1-flabol","2026-10-04T18:00","2026-10-05T17:59"),
   ("ewc-pres-bra-2026-10-04-luisil","2026-10-04T18:00","2026-10-05T17:59"),
   ("apdc-trumpadmin-2026-karlea","2026-08-12T00:00","2026-08-12T23:59"),
   ("apdc-katzac-presssec-2026-10-31","2026-10-16T00:00","2026-10-16T23:59"),
   ("apdc-katzac-presssec-2026-12-31","2026-10-16T00:00","2026-10-16T23:59"),
   ("gsc-usfedgvmt-by-2026-10-01","2026-09-30T12:00","2026-10-01T11:59"),
   ("ewc-pres-bra-2026-10-04-luisil","2026-10-25T00:00","2026-10-25T23:59"),
   ("ewc-pres-bra-2026-10-04-flabol","2026-10-25T00:00","2026-10-25T23:59"),
   ("parc-trmpapprv-wk-2026-10-23-38pt6-38pt8","2026-10-22T00:00","2026-10-22T23:59"),
]
out={}
for s,a,b in W:
    h=get("https://gateway.polymarket.us/v1/price-history",{"symbol":s,"timestamp.startTimestamp":ts(a),"timestamp.endTimestamp":ts(b),"fidelity":1})
    pts=[(int(x["timestamp"]),float(x.get("longPrice") or 0)) for x in (h or {}).get("history",[])]
    out[f"{s}|{a}"]=pts; print(s,a,len(pts),flush=True)
json.dump(out,open("../raw/minute.json","w"))
