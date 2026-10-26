import json, sys, datetime
sys.path.insert(0, sys.argv[1]); import gw
evs = json.load(open(sys.argv[2]))['events']
G='https://gateway.polymarket.us'
def ts(s): return int(datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())
out = {}
for e in evs:
    if not e['slug'].startswith('usgas'): continue
    es, ee = ts(e['startDate']), ts(e['endDate'])
    if e['slug'].startswith(('usgas-highm','usgas-lowm')): es = ee - 86400*20
    for m in e['markets']:
        hs = []
        a = min(es, ee - 86400)
        for (s0, s1) in [(a, a+86400), (a+86400, ee+16*3600)]:
            if s1 <= s0: continue
            h,_ = gw.get(f"{G}/v1/price-history?symbol={m['slug']}&timestamp.startTimestamp={s0}&timestamp.endTimestamp={s1}&fidelity=1")
            hs += (h or {}).get('history', [])
        st,_ = gw.get(f"{G}/v1/markets/{m['slug']}/settlement")
        bbo,_ = gw.get(f"{G}/v1/markets/{m['slug']}/bbo")
        out[m['slug']] = {'event': e['slug'], 'es': es, 'ee': ee, 'q': m.get('subtitle') or m.get('question'), 'desc': m.get('description'), 'mend': m.get('endDate'), 'hist': hs, 'settle': st, 'bbo': bbo}
json.dump(out, open(sys.argv[3], 'w'))
print(len(out))
