import sys, json; sys.path.insert(0, sys.argv[1]); from g import get
out=[]; off=0
while True:
    d=get("https://gateway.polymarket.us/v1/events", {"closed":"false","limit":500,"offset":off})
    ev=(d or {}).get("events") or []
    out+=ev; print(off,len(ev),file=sys.stderr)
    if len(ev)<500: break
    off+=500
json.dump(out, open(sys.argv[2],"w"))
print(len(out))
