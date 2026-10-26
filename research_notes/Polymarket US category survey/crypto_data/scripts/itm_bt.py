"""Hourly/daily ladder 'deep-ITM at the ask' rule with realistic delays.
Decide at quote time tq using spot read at tq-LAG; execute at the ask/bid shown DELAY seconds later (next bar)."""
import json, math, bisect, collections, datetime as dt, sys
from statistics import NormalDist
N = NormalDist().cdf
fee = lambda p: 0.0695 * p * (1 - p)
exec(open('scripts/ladder_bt.py').read().split('obs = []')[0])  # reuse loaders (spot, rv, dvol, ph)
STRICT = False
def run(hourly, taus, LAG, DELAY, vol='rv1h', minp=0.80, thr=0.02, volmult=1.0):
    pn = collections.defaultdict(list); allp = []
    for slug, d in ph.items():
        if ('above-hr' in slug) != hourly or not d['h']: continue
        m = d['meta']; we = ts(m['we']); K = float(m['strike']); y = float(m['sp']) >= K
        bars = sorted(d['h'], key=lambda x: x['timestamp']); bt = [x['timestamp'] + 60 for x in bars]
        for tau in taus:
            i = bisect.bisect_right(bt, we - tau) - 1
            if i < 0 or (we - tau) - bt[i] > 120: continue
            tq = bt[i]; x = bars[i]
            S = spot(tq - LAG)
            s = rv(tq - LAG, 3600) if vol == 'rv1h' else (rv(tq - LAG, 86400) if vol == 'rv24h' else dvol(tq))
            if not S or not s: continue
            s *= volmult
            p = N(math.log(S / K) / (s * math.sqrt(max(we - tq - 40, 1) / 31536000)))
            # execution bar
            j = bisect.bisect_left(bt, tq + DELAY) if DELAY else i
            if j >= len(bars) or bt[j] > we - 60: continue
            xe = bars[j]; ask = xe['longPrice']; bid = 1 - xe['shortPrice']
            a0 = x['longPrice']; b0 = 1 - x['shortPrice']
            if STRICT and not (0 < a0 - b0 <= 0.08 and 0 < ask - bid <= 0.08): continue
            if a0 >= minp and a0 < 0.99 and p - a0 - fee(a0) > thr and ask < 0.995:
                v = y - ask - fee(ask); pn[m['event']].append(v); allp.append((v, ask, p))
            elif 1 - b0 >= minp and 1 - b0 < 0.99 and b0 - p - fee(b0) > thr and bid > 0.005:
                v = (1 - y) - (1 - bid) - fee(bid); pn[m['event']].append(v); allp.append((v, 1 - bid, 1 - p))
    if not allp: return 'none'
    n = len(allp); mu = sum(v for v, _, _ in allp) / n
    g = [sum(v) - mu * len(v) for v in pn.values()]
    se = math.sqrt(sum(z * z for z in g)) / n * math.sqrt(len(g) / max(1, len(g) - 1))
    losses = sum(1 for v, _, _ in allp if v < 0)
    return f'trades {n:4d} ladders {len(pn):3d} mean {mu:+.4f} se {se:.4f} losses {losses} avg cost {sum(c for _, c, _ in allp)/n:.3f} avg model {sum(q for _, _, q in allp)/n:.4f}'
print('HOURLY, buy side priced >=0.80 when model(rv1h) edge > 2c')
for taus in ((900,), (1800,), (900, 1800, 2700)):
    for LAG, DELAY in ((5, 0), (60, 0), (5, 60), (60, 60), (120, 120)):
        print(f' taus {taus} spot-lag {LAG:3d}s exec-delay {DELAY:3d}s: {run(True, taus, LAG, DELAY)}')
print('HOURLY vol sensitivity (taus 15/30/45m, lag 60, delay 60)')
for vol, mult in (('rv1h', 1.0), ('rv1h', 1.5), ('rv24h', 1.0), ('dvol', 1.0), ('dvol', 0.8)):
    print(f'  {vol} x{mult}: {run(True, (900, 1800, 2700), 60, 60, vol, volmult=mult)}')
print('HOURLY min price 0.90 / thr 0.04')
print('  ', run(True, (900, 1800, 2700), 60, 60, minp=0.90, thr=0.04))
print('DAILY (taus 2h/4h/6h, lag 60, delay 60)')
for vol in ('rv1h', 'rv24h', 'dvol'):
    print(f'  {vol}: {run(False, (7200, 14400, 21600), 60, 60, vol)}')

STRICT = True
print('\nSTRICT (both bars two-sided, 0 < spread <= 8c)')
for taus in ((900,), (1800,), (900, 1800, 2700)):
    print(f' hourly taus {taus} lag60 delay60 rv1h: {run(True, taus, 60, 60)}')
    print(f' hourly taus {taus} lag60 delay60 dvol: {run(True, taus, 60, 60, "dvol")}')
print(' daily rv24h:', run(False, (7200, 14400, 21600), 60, 60, 'rv24h'))
print(' daily dvol :', run(False, (7200, 14400, 21600), 60, 60, 'dvol'))
