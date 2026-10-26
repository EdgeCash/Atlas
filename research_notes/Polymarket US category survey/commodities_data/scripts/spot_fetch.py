import json, sys
sys.path.insert(0, sys.argv[1]); import gw
start, end = int(sys.argv[2]), int(sys.argv[3]); step = 3600*5  # 5S bucket, 3600 candles
out = {}
for a in ['commodity:gold', 'commodity:silver']:
    c = []
    t = start
    while t < end:
        d,_ = gw.get(f'https://gateway.polymarket.us/v1/asset-prices/history?assets={a}&from={t}&to={min(t+step-5,end)}&bucket=ASSET_PRICE_BUCKET_5S')
        if d and d.get('series'): c += d['series'][0]['candles']
        t += step
    out[a] = c
    print(a, len(c))
json.dump(out, open(sys.argv[4], 'w'))
