import json, sys, math, statistics as S, datetime
sys.path.insert(0, 'scripts'); import gw
recs = [json.loads(l) for l in open('raw/live_book.jsonl')]
G = 'https://gateway.polymarket.us'
t0 = int(min(r['ws'] for r in recs)) - 3600; t1 = int(max(r['t'] for r in recs)) + 5
spot = {}
for m in ['gold', 'silver']:
    c = []
    t = t0
    while t < t1:
        d, _ = gw.get(f'{G}/v1/asset-prices/history?assets=commodity:{m}&from={t}&to={min(t+3600*5-5, t1)}&bucket=ASSET_PRICE_BUCKET_5S')
        c += d['series'][0]['candles'] if d and d.get('series') else []
        t += 3600*5
    spot[m] = [(x['timestamp'], float(x['open']), float(x['close'])) for x in c if x['tickCount'] > 0]
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
ptb = {}
for r in recs:
    if r['slug'] in ptb: continue
    e, _ = gw.get(f"{G}/v1/events?slug={r['slug'].split('-',1)[1]}")
    try: ptb[r['slug']] = float(e['events'][0]['markets'][0]['assetPriceTerms']['priceToBeat']['value'])
    except Exception: ptb[r['slug']] = None
    st, _ = gw.get(f"{G}/v1/markets/{r['slug']}/settlement"); ptb[r['slug']+'_y'] = (st or {}).get('settlement')
for r in recs:
    m = r['metal']; s0 = ptb.get(r['slug'])
    sp = ((r['spot'] or {}).get('series') or [{}])[0].get('candles', [])
    sp = [x for x in sp if x['tickCount'] > 0]
    if not sp or not s0: continue
    St = float(sp[-1]['close']); tau = r['ws'] + 900 - r['t']
    hist = [x for x in spot[m] if r['t']-3600 <= x[0] < r['t']]
    rr = [math.log(b[2]/a[2]) for a, b in zip(hist, hist[1:]) if b[0]-a[0] == 5]
    var = sum(x*x for x in rr)/len(rr)/5
    p = Phi(math.log(St/s0)/math.sqrt(var*tau))
    bk = (r['book'] or {}).get('marketData', {})
    bids = [(float(l['px']['value']), float(l['qty'])) for l in bk.get('bids', [])]
    offs = [(float(l['px']['value']), float(l['qty'])) for l in bk.get('offers', [])]
    # Up side buy = lift offers; Down side buy = hit bids (BUY_SHORT at 1-bid)
    up97 = sum(q for px, q in offs if px <= 0.97); dn97 = sum(q for px, q in bids if px >= 0.03)
    fav = 'UP' if p >= 0.5 else 'DN'; pf = max(p, 1-p)
    avail = up97 if fav == 'UP' else dn97
    best = (offs[0] if offs else None) if fav == 'UP' else ((round(1-bids[0][0], 2), bids[0][1]) if bids else None)
    print(f"{datetime.datetime.fromtimestamp(r['t'], datetime.UTC).strftime('%H:%M:%S')} {m:6s} tau {tau:5.0f}s p(fav) {pf:.3f} {fav} best fav ask {best} qty at <=0.97 {avail:7.1f} cacheAge {r['age']} settle {ptb.get(r['slug']+'_y')}")
