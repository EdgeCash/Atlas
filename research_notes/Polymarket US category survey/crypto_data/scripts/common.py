import json,urllib.request,time,sys
G='https://gateway.polymarket.us'
import os
SP=float(os.environ.get("GW_SPACING","0.5"))
_last=[0.0]
def get(u,gateway=None,timeout=40):
    gw = u.startswith(G) if gateway is None else gateway
    for i in range(7):
        if gw:
            dt=time.time()-_last[0]
            if dt<SP: time.sleep(SP-dt)
            _last[0]=time.time()
        try:
            r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'atlas-research'}),timeout=timeout)
            return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429 or e.code>=500:
                time.sleep(min(30,2**i)); continue
            if e.code==404: return None
            raise
        except Exception as e:
            time.sleep(2**i)
    return None
