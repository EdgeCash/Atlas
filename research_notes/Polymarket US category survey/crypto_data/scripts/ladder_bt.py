"""Backtest: settled BTC hourly/daily above-ladders. Model fair from BRTI + vol (realized or DVOL) vs PMUS bid/ask
(price-history bars; the bar stamped t is the book at t+60). Taker trades when model edge after fee > thr."""
import json, math, bisect, collections, datetime as dt, sys
from statistics import NormalDist
N = NormalDist().cdf
THETA = 0.0695
fee = lambda p: THETA * p * (1 - p)
ph = json.load(open('raw/ph_ladder.json'))
B = json.load(open('raw/brti_5s.json'))['btc']
bk = sorted(int(k) for k in B); bv = [B[str(k)][0] for k in bk]
r2 = [0.0] * len(bv)
for i in range(1, len(bv)):
    r2[i] = r2[i - 1] + (math.log(bv[i] / bv[i - 12]) ** 2 / 12 if i >= 12 else 0.0)
dv = {int(x[0] / 1000): x[4] / 100 for x in json.load(open('raw/dvol_btc.json'))['result']['data']}
dvk = sorted(dv)
ts = lambda s: int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp())

def spot(t):
    i = bisect.bisect_right(bk, t) - 1
    return bv[i] if i >= 0 else None

def rv(t, win):
    i = bisect.bisect_right(bk, t) - 1; j = bisect.bisect_right(bk, t - win) - 1
    if j < 1 or i - j < 50: return None
    return math.sqrt((r2[i] - r2[j]) / (5 * (i - j)) * 31536000)

def dvol(t):
    i = bisect.bisect_right(dvk, t) - 1
    return dv[dvk[i]] if i >= 0 else None

obs = []
for slug, d in ph.items():
    m = d['meta']; h = d['h']
    if not h: continue
    we = ts(m['we']); K = float(m['strike']); y = float(m['sp']) >= K
    hourly = 'above-hr' in slug
    taus = (3600, 1800, 900) if hourly else (12 * 3600, 6 * 3600, 2 * 3600)
    bars = sorted(h, key=lambda x: x['timestamp'])
    bt = [x['timestamp'] + 60 for x in bars]
    for tau in taus:
        i = bisect.bisect_right(bt, we - tau) - 1
        if i < 0 or (we - tau) - bt[i] > 120: continue
        x = bars[i]; tq = bt[i]
        ask = x['longPrice']; bid = 1 - x['shortPrice']
        if not ask or ask >= 0.995 or bid <= 0.005 or ask - bid > 0.5: continue
        S = spot(tq - 5)
        if not S: continue
        tt = we - tq
        vols = {'rv1h': rv(tq - 5, 3600), 'rv24h': rv(tq - 5, 86400), 'dvol': dvol(tq)}
        o = dict(slug=slug, event=m['event'], hourly=hourly, tau=tau, K=K, S=S, y=y, ask=ask, bid=bid)
        for k, s in vols.items():
            if s: o['p_' + k] = N(math.log(S / K) / (s * math.sqrt(max(tt - 40, 1) / 31536000)))
        obs.append(o)

def stats(xs, key):
    pn = []
    by = collections.defaultdict(list)
    for o in xs:
        p = o.get(key)
        if p is None: continue
        ey = p - o['ask'] - fee(o['ask']); en = o['bid'] - p - fee(o['bid'])
        if ey > THR: v = o['y'] - o['ask'] - fee(o['ask'])
        elif en > THR: v = (1 - o['y']) - (1 - o['bid']) - fee(o['bid'])
        else: continue
        pn.append(v); by[o['event']].append(v)
    if not pn: return 'none'
    m = sum(pn) / len(pn)
    # cluster SE by ladder (event)
    g = [sum(v) - m * len(v) for v in by.values()]
    se = math.sqrt(sum(x * x for x in g)) / len(pn) * math.sqrt(len(g) / max(1, len(g) - 1))
    return f'trades {len(pn)} ladders {len(by)} mean {m:+.4f} se {se:.4f}'

for hourly in (True, False):
    print('==', 'HOURLY' if hourly else 'DAILY', 'ladders', len({o['event'] for o in obs if o['hourly'] == hourly}))
    for tau in sorted({o['tau'] for o in obs if o['hourly'] == hourly}, reverse=True):
        xs = [o for o in obs if o['hourly'] == hourly and o['tau'] == tau]
        sp = sorted(o['ask'] - o['bid'] for o in xs)
        bm = sum(((o['ask'] + o['bid']) / 2 - o['y']) ** 2 for o in xs) / len(xs)
        line = f' tau {tau/60:.0f}m n={len(xs)} med spread {sp[len(sp)//2]:.3f} Brier mid {bm:.4f}'
        for k in ('p_rv1h', 'p_rv24h', 'p_dvol'):
            zs = [o for o in xs if k in o]
            if zs: line += f' | {k[2:]} {sum((o[k]-o["y"])**2 for o in zs)/len(zs):.4f}'
        print(line)
        for k in ('p_rv1h', 'p_rv24h', 'p_dvol'):
            for THR in (0.0, 0.02, 0.05):
                print(f'    {k[2:]:6s} thr {THR:.2f}: {stats(xs, k)}')

# ---- detail: hourly, rv1h, edge>thr at 15 and 30 min
import itertools
print('\nDETAIL hourly rv1h')
def detail(tau, thr):
    rows = []
    for o in obs:
        if not o['hourly'] or o['tau'] != tau or 'p_rv1h' not in o: continue
        p = o['p_rv1h']
        ey = p - o['ask'] - fee(o['ask']); en = o['bid'] - p - fee(o['bid'])
        if ey > thr: rows.append(('Yes', o['ask'], p, o['y'] - o['ask'] - fee(o['ask']), o))
        elif en > thr: rows.append(('No', 1 - o['bid'], 1 - p, (1 - o['y']) - (1 - o['bid']) - fee(o['bid']), o))
    return rows
for tau in (900, 1800):
    for thr in (0.02, 0.05):
        rows = detail(tau, thr)
        print(f' tau {tau//60}m thr {thr}: n={len(rows)}')
        for lab, f in (('buy Yes', lambda r: r[0] == 'Yes'), ('buy No', lambda r: r[0] == 'No'),
                       ('cost<0.2', lambda r: r[1] < 0.2), ('cost 0.2-0.8', lambda r: 0.2 <= r[1] <= 0.8), ('cost>0.8', lambda r: r[1] > 0.8),
                       ('first half', lambda r: r[4]['event'] < sorted({o['event'] for o in obs if o['hourly']})[32]),
                       ('second half', lambda r: r[4]['event'] >= sorted({o['event'] for o in obs if o['hourly']})[32])):
            xs = [r for r in rows if f(r)]
            if xs:
                m = sum(r[3] for r in xs) / len(xs)
                print(f'    {lab:12s} n={len(xs):4d} mean pnl {m:+.4f} mean cost {sum(r[1] for r in xs)/len(xs):.3f} mean model {sum(r[2] for r in xs)/len(xs):.3f} win {sum(r[3]>0 for r in xs)/len(xs):.2f} ladders {len({r[4]["event"] for r in xs})}')
# quote persistence: was the same ask still there one bar later?
