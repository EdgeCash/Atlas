import time, json, urllib.request, urllib.parse, urllib.error
_l=[0.0]
def kget(path, params=None, minint=2.5):
    url="https://api.elections.kalshi.com/trade-api/v2"+path+("?"+urllib.parse.urlencode(params) if params else "")
    for i in range(8):
        dt=time.time()-_l[0]
        if dt<minint: time.sleep(minint-dt)
        _l[0]=time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"research"}),timeout=60) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(5*(i+1)); continue
            if e.code==404: return None
            raise
    return None
