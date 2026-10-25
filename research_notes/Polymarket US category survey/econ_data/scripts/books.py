import json, time, urllib.request, sys, datetime
ev=json.load(open(sys.argv[1])); outp=sys.argv[2]
skip=('usgas','usbeef')
res={}
mk=[(e['slug'],m['slug']) for e in ev if not e['slug'].startswith(skip) for m in e['markets']]
print(len(mk),file=sys.stderr)
for es,s in mk:
    url=f"https://gateway.polymarket.us/v1/markets/{s}/book"
    for a in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r: d=json.load(r); break
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(a+1)); continue
            d={'err':e.code}; break
        except Exception as e:
            d={'err':str(e)}; time.sleep(2)
    d['_fetched']=datetime.datetime.utcnow().isoformat()+'Z'; d['_event']=es
    res[s]=d; time.sleep(0.55)
json.dump(res,open(outp,'w'))
