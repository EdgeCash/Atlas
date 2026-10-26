import json, math, bisect, statistics as S, collections, sys
d = json.load(open('raw/metals_hist.json')); sp = json.load(open('raw/spot5s.json'))
FEE = 0.0695
def fee(p): return FEE*p*(1-p)
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
spot = {}
for a, c in sp.items():
    ts = [x['timestamp'] for x in c if x['tickCount'] > 0]
    op = [float(x['open']) for x in c if x['tickCount'] > 0]
    cl = [float(x['close']) for x in c if x['tickCount'] > 0]
    spot[a.split(':')[1]] = (ts, op, cl)
def px_at(metal, t):  # last close at or before t (candle start <= t-5)
    ts, op, cl = spot[metal]; i = bisect.bisect_right(ts, t-5) - 1
    return cl[i] if i >= 0 else None
def rv(metal, t, lookback=3600):  # per-second variance from 5s log returns
    ts, op, cl = spot[metal]; j = bisect.bisect_right(ts, t-5); i = bisect.bisect_left(ts, t-lookback)
    r = [math.log(cl[k]/cl[k-1]) for k in range(max(i,1), j) if ts[k]-ts[k-1] == 5]
    if len(r) < 60: return None
    return sum(x*x for x in r)/len(r)/5.0
# 1) ptb check
chk = collections.Counter()
for k, v in d.items():
    metal = 'gold' if 'gold' in k else 'silver'
    ts, op, cl = spot[metal]
    if v['ptb']:
        i = bisect.bisect_left(ts, v['ws'])
        if i < len(ts) and ts[i] == v['ws']:
            chk['match' if abs(op[i]-float(v['ptb']['value'])) < 1e-9 else 'diff'] += 1
        else: chk['nocandle'] += 1
print('ptb vs 5s candle open:', chk)
gvz = 0.2434  # GVZ 23 Oct close
rows = []
for k, v in d.items():
    if not v['ptb'] or not v['settle']: continue
    metal = 'gold' if 'gold' in k else 'silver'
    y = v['settle']['settlement']; s0 = float(v['ptb']['value'])
    h = sorted((v['hist'] or {}).get('history', []), key=lambda x: x['timestamp'])
    for x in h:
        t = x['timestamp']
        if not (v['ws']+60 <= t < v['we']): continue
        tau = v['we'] - t; St = px_at(metal, t); var = rv(metal, t)
        if St is None or var is None: continue
        z = math.log(St/s0)/math.sqrt(var*tau) if var > 0 else 0
        p = Phi(z)
        rows.append(dict(slug=k, series=v['series'], metal=metal, t=t, tau=tau, p=p, ask_up=x['longPrice'], ask_dn=x['shortPrice'], y=y))
json.dump(rows, open('raw/metals_rows.json', 'w'))
print('rows', len(rows))
# calibration of model and market
def brier(ps, ys): return sum((p-y)**2 for p, y in zip(ps, ys))/len(ps)
for ser in sorted(set(r['series'] for r in rows)):
    R = [r for r in rows if r['series'] == ser and 0 < r['ask_up'] < 1 and 0 < r['ask_dn'] < 1]
    if not R: continue
    mid = [(r['ask_up'] + 1 - r['ask_dn'])/2 for r in R]
    print(ser, 'n', len(R), 'windows', len(set(r['slug'] for r in R)), 'Brier model', round(brier([r['p'] for r in R], [r['y'] for r in R]), 4), 'market mid', round(brier(mid, [r['y'] for r in R]), 4), 'median spread', S.median([r['ask_up'] + r['ask_dn'] - 1 for r in R]))
# taker strategy: buy side if model edge after fee > thr; one entry per window (first signal), and all-signal variant
for thr in [0.0, 0.03, 0.05, 0.10]:
    for lag in [0, 1]:
        res = collections.defaultdict(list)
        byw = collections.defaultdict(list)
        for r in rows: byw[r['slug']].append(r)
        for slug, R in byw.items():
            R.sort(key=lambda r: r['t'])
            for i, r in enumerate(R):
                q = R[i+lag] if i+lag < len(R) else None
                if q is None: continue
                for side in ('up', 'dn'):
                    p = r['p'] if side == 'up' else 1-r['p']
                    a = r['ask_up'] if side == 'up' else r['ask_dn']   # decision price
                    ae = q['ask_up'] if side == 'up' else q['ask_dn']  # execution price
                    if not (0.02 <= a <= 0.98) or not (0 < ae < 1): continue
                    if p - a - fee(a) > thr:
                        win = r['y'] == 1 if side == 'up' else r['y'] == 0
                        res[r['series']].append(((1 if win else 0) - ae - fee(ae), ae, slug))
                        break
                else: continue
                break
        for ser, L in sorted(res.items()):
            pl = [x[0] for x in L]
            print(f'thr {thr} lag {lag} {ser:18s} trades {len(L):3d} mean P&L/contract {S.mean(pl):+.3f} sd {S.pstdev(pl):.3f} se {S.pstdev(pl)/math.sqrt(len(pl)):.3f} hit {sum(1 for x in pl if x>0)}/{len(pl)} mean ask {S.mean(x[1] for x in L):.2f}')
