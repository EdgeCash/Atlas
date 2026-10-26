import json, time, ssl, urllib.request, urllib.error, os
CTX = ssl.create_default_context(cafile='/root/.ccr/ca-bundle.crt')
_last = [0.0]
MIN_GAP = 0.6  # <=~1.7 req/s
def get(url, tries=6):
    for i in range(tries):
        gap = time.time() - _last[0]
        if gap < MIN_GAP: time.sleep(MIN_GAP - gap)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 research'})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode()), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** i); continue
            if e.code == 404: return None, {}
            raise
        except Exception:
            time.sleep(2 ** i)
    return None, {}
