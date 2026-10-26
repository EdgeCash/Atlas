import time, json, sys, urllib.request, urllib.parse, urllib.error
_last=[0.0]
def get(url, params=None, minint=0.55, tries=6):
    if params: url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    for i in range(tries):
        dt = time.time()-_last[0]
        if dt < minint: time.sleep(minint-dt)
        _last[0]=time.time()
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 research","Accept":"application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code==429 or e.code>=500:
                time.sleep(2*(i+1)); continue
            if e.code==404: return None
            raise
        except Exception as e:
            time.sleep(2*(i+1))
    return None
