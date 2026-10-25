import json, sys, datetime, time
sys.path.insert(0, sys.argv[1]); import gw
evs = json.load(open(sys.argv[2]))['events']
G='https://gateway.polymarket.us'
def ts(s): return int(datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())
out = {}
for e in evs:
    if not (e.get('seriesSlug') or '').startswith(('gold','silver')): continue
    for m in e['markets']:
        if m.get('status') != 'MARKET_STATUS_RESOLVED': continue
        a = m['assetPriceTerms']; ws, we = ts(a['windowStart']), ts(a['windowEnd'])
        h,_ = gw.get(f"{G}/v1/price-history?symbol={m['slug']}&timestamp.startTimestamp={ws-300}&timestamp.endTimestamp={min(we+1800, ws+86400)}&fidelity=1")
        st,_ = gw.get(f"{G}/v1/markets/{m['slug']}/settlement")
        bbo,_ = gw.get(f"{G}/v1/markets/{m['slug']}/bbo")
        out[m['slug']] = {'series': e['seriesSlug'], 'ws': ws, 'we': we, 'ptb': a.get('priceToBeat'), 'sp': a.get('settlementPrice'), 'hist': h, 'settle': st, 'bbo': bbo}
json.dump(out, open(sys.argv[3], 'w'))
print(len(out))
