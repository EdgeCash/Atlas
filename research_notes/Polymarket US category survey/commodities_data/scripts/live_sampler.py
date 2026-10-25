import json, sys, time, math, datetime
sys.path.insert(0, sys.argv[1]); import gw
gw.MIN_GAP = 1.0
G = 'https://gateway.polymarket.us'; out = open(sys.argv[2], 'a'); end = time.time() + float(sys.argv[3])
def slug(metal, ws):
    t = datetime.datetime.fromtimestamp(ws, datetime.UTC).strftime('%Y-%m-%d-%H%Mz')
    return ('cpausp-gold' if metal == 'gold' else 'cpagsp-silver') + '-updown-15m-' + t
while time.time() < end:
    now = time.time(); ws = int(now // 900 * 900); tau = ws + 900 - now
    if tau > 330: time.sleep(min(tau - 330, 30)); continue
    for metal in ['gold', 'silver']:
        s = slug(metal, ws)
        sp, _ = gw.get(f'{G}/v1/asset-prices/history?assets=commodity:{metal}&from={int(now)-3}&to=0&bucket=ASSET_PRICE_BUCKET_1S')
        bk, hd = gw.get(f'{G}/v1/markets/{s}/book')
        m, _ = gw.get(f'{G}/v1/markets?slug={s}') if False else (None, None)
        out.write(json.dumps({'t': now, 'tau': tau, 'metal': metal, 'slug': s, 'ws': ws, 'spot': sp, 'book': bk, 'age': hd.get('Age')}) + '\n'); out.flush()
    time.sleep(8)
