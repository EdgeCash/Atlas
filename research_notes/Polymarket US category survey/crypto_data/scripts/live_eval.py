"""Evaluate live hourly-ladder forward test: deep-ITM asks (two-sided real books) vs model and outcome."""
import json, sys, os, time, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
from common import get, G
fee = lambda p: 0.0695 * p * (1 - p)
rows = [json.loads(l) for l in open('raw/live_itm.jsonl')]
obs = [r for r in rows if 'K' in r]
lads = sorted({r['ladder'] for r in obs})
sp = {}
for l in lads:
    T = int(dt.datetime.strptime(l[-16:], '%Y-%m-%d-%H%Mz').replace(tzinfo=dt.timezone.utc).timestamp())
    if time.time() < T + 5: continue
    r = get(G + f'/v1/asset-prices/history?assets=crypto:btc&from={T-60}&to={T-1}&bucket=ASSET_PRICE_BUCKET_1S')
    c = [float(x['close']) for x in r['series'][0]['candles']]
    sp[l] = round(sum(c) / len(c), 2) if len(c) == 60 else None
print('settlement (avg of 60 BRTI 1s closes):', sp)
print('ladder chk K | bid ask (sizes) | p_rv p_dv | side cost | EV rv / dv (c) | outcome pnl')
tot = []
for r in obs:
    l = r['ladder']
    if l not in sp or sp[l] is None: continue
    y = sp[l] >= r['K']
    a = r['offers'][0] if r['offers'] else None; b = r['bids'][0] if r['bids'] else None
    if not (a and b): continue
    for side, cost, pr, pd, win in (('Yes', a[0], r['p_rv'], r['p_dv'], y), ('No', 1 - b[0], 1 - r['p_rv'], 1 - r['p_dv'], not y)):
        if not (0.80 <= cost <= 0.99): continue
        evr = pr - cost - fee(cost); evd = pd - cost - fee(cost)
        if evr > 0.02:
            pnl = win - cost - fee(cost); tot.append((pnl, evd > 0.0, r['chk']))
            print(f"{l[-5:]} {r['chk']:5d} {int(r['K'])} | {b} {a} | {r['p_rv']:.3f} {r['p_dv']:.3f} | {side} {cost:.2f} | {evr*100:+.1f} / {evd*100:+.1f} | {int(win)} {pnl*100:+.1f}")
if tot:
    print('signals', len(tot), 'mean pnl %.4f' % (sum(p for p, _, _ in tot) / len(tot)), 'losses', sum(p < 0 for p, _, _ in tot),
          '| also DVOL-positive:', sum(1 for _, d, _ in tot if d), 'mean pnl %.4f' % (sum(p for p, d, _ in tot if d) / max(1, sum(1 for _, d, _ in tot if d))))
