"""Forward test on live books: BTC hourly above-ladders at 45/30/20/15/10/5 min before expiry.
Records real /book top levels, BRTI, rv1h and DVOL; after expiry records settlementPrice. Read-only."""
import json, sys, os, time, math, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
from common import get, G
from statistics import NormalDist
N = NormalDist().cdf
OUT = sys.argv[1]; NLAD = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CHK = (2700, 1800, 1200, 900, 600, 300)
ts = lambda s: int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp())

def log(o):
    with open(OUT, 'a') as f: f.write(json.dumps(o) + '\n')

def brti_state():
    n = int(time.time())
    r = get(G + f'/v1/asset-prices/history?assets=crypto:btc&from={n-3600}&to=0&bucket=ASSET_PRICE_BUCKET_5S')
    c = [float(x['close']) for x in r['series'][0]['candles']]
    rr = [math.log(c[i] / c[i - 12]) ** 2 / 12 for i in range(12, len(c))]
    s = math.sqrt(sum(rr) / (5 * len(rr)) * 31536000)
    return c[-1], s

def dvol():
    n = int(time.time() * 1000)
    r = get(f'https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=60&start_timestamp={n-600000}&end_timestamp={n}', gateway=False)
    return r['result']['data'][-1][4] / 100

lst = get(G + '/v1/events?closed=false&limit=500&offset=0&categories=crypto')
now = time.time()
lads = sorted([e for e in lst['events'] if e['slug'].startswith('btc-above-hr') and ts(e['endDate']) - now > 300], key=lambda e: e['endDate'])[:NLAD]
plan = sorted((ts(e['endDate']) - c, e['slug'], c) for e in lads for c in CHK if ts(e['endDate']) - c > now)
log({'plan': [(p[1], p[2]) for p in plan], 'start': now})
done_slugs = set()
for t_at, slug, c in plan:
    while time.time() < t_at: time.sleep(2)
    e = get(G + f'/v1/events?slug={slug}')['events'][0]
    we = ts(e['endDate'])
    S, s1 = brti_state(); dv = dvol()
    for m in e['markets']:
        K = float(m['assetPriceTerms']['strike']['value'])
        if abs(K / S - 1) > 0.012: continue
        b = get(G + f"/v1/markets/{m['slug']}/book")
        md = (b or {}).get('marketData') or {}
        tau = we - time.time()
        z = lambda sig: N(math.log(S / K) / (sig * math.sqrt(max(tau - 40, 1) / 31536000)))
        log({'ladder': slug, 'chk': c, 't': time.time(), 'K': K, 'S': S, 'rv1h': s1, 'dvol': dv, 'p_rv': z(s1), 'p_dv': z(dv),
             'bids': [(float(x['px']['value']), float(x['qty'])) for x in md.get('bids', [])[:3]],
             'offers': [(float(x['px']['value']), float(x['qty'])) for x in md.get('offers', [])[:3]]})
# settlements
time.sleep(max(0, max(ts(e['endDate']) for e in lads) + 1200 - time.time()))
for e in lads:
    r = get(G + f"/v1/events?slug={e['slug']}")
    ms = r['events'][0]['markets'] if r and r.get('events') else []
    sp = [((m.get('assetPriceTerms') or {}).get('settlementPrice') or {}).get('value') for m in ms]
    log({'settle': e['slug'], 'sp': next((x for x in sp if x), None)})
log({'end': time.time()})
