import sys, time, json, requests, os
V='/root/.ccr/ca-bundle.crt'; G='https://gateway.polymarket.us'
s = requests.Session(); s.verify = V
out = open(sys.argv[1], 'a')
# find live markets in these leagues
slugs = []
for lg in ['itfme','itfwo','setkameua','setkamecz','setkamemd','cs2','czechligapro','utr','ttelite','wtt','lol','ebfsa','ebb']:
    try:
        evs = s.get(f'{G}/v2/leagues/{lg}/events', params={'limit':50}, timeout=30).json().get('events') or []
    except Exception as e:
        continue
    for e in evs:
        if e.get('live'):
            slugs.append((lg, 'aec-'+str(e.get('slug')), e.get('period'), e.get('score')))
print('live', slugs, file=out, flush=True)
slugs = slugs[:10]
t0 = time.time()
while time.time() - t0 < 150:
    for lg, slug, *_ in slugs:
        try:
            d = s.get(f'{G}/v1/markets/{slug}/bbo', timeout=15).json().get('marketData') or {}
        except Exception as e:
            d = {'err': str(e)[:80]}
        print(json.dumps({'t': round(time.time()-t0,1), 'lg': lg, 'slug': slug, 'bbo': d}), file=out, flush=True)
    time.sleep(5)
