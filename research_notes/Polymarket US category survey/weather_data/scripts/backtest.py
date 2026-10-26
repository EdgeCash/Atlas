import sys, json, os, math, collections, datetime as dt
sys.path.insert(0, 'scripts')
from model import dist, bucket_probs, fee
nbs = {tuple(k.split('|')): v for k, v in json.load(open('raw/nbs_txn.json')).items()}
ev = json.load(open('raw/events.json'))
H = {}
def hist(slug):
    if slug not in H:
        fn = f'raw/hist60/{slug}.json'
        H[slug] = {x['timestamp']: (x.get('longPrice'), x.get('shortPrice')) for x in json.load(open(fn)).get('history', [])} if os.path.exists(fn) else None
    return H[slug]
def px(s, t):
    for i in range(0, 3):
        v = s.get(t - 3600 * i)
        if v: return v
    return None
SETUPS = {'T1 D-1 20Z (NBS D-1 18Z)': ('D-1 18Z', -1, 18, 20), 'T2 D 14Z (NBS D 12Z)': ('D 12Z', 0, 12, 14)}
recs = []
for e in ev:
    if e['kind'] != 'high': continue
    D = dt.date.fromisoformat(e['date'])
    if D < dt.date(2026, 5, 25): continue
    hs = [hist(b['slug']) for b in e['buckets']]
    if not all(hs): continue
    for name, (lead, dd, rh, th) in SETUPS.items():
        rt = (D + dt.timedelta(days=dd)).strftime('%Y-%m-%d') + f' {rh:02d}'
        ft = (D + dt.timedelta(days=1)).strftime('%Y-%m-%d') + ' 00'
        f = nbs.get((e['station'], rt, ft))
        if not f: continue
        t = int(dt.datetime.combine(D + dt.timedelta(days=dd), dt.time(th), dt.timezone.utc).timestamp())
        pr = [px(h, t) for h in hs]
        if not all(pr): continue
        d = dist('high', lead, e['station'], before=e['date'])
        q = bucket_probs(f[0], d, [(b['lo'], b['hi']) for b in e['buckets']])
        for b, p, qq in zip(e['buckets'], pr, q):
            ya, na = p
            recs.append(dict(setup=name, station=e['station'], date=e['date'], lo=b['lo'], hi=b['hi'], won=b['won'], q=qq, yes_ask=ya, no_ask=na, mid=(ya + 1 - na) / 2 if ya is not None and na is not None else None))
json.dump(recs, open('raw/bt_recs.json', 'w'))
for name in SETUPS:
    R = [r for r in recs if r['setup'] == name]
    nev = len({(r['station'], r['date']) for r in R})
    print(f'===== {name}: events {nev}, buckets {len(R)}')
    # scoring on events: log loss of winning bucket
    byev = collections.defaultdict(list)
    for r in R: byev[(r['station'], r['date'])].append(r)
    llm = llk = brm = brk = 0; n = 0
    for k, rs in byev.items():
        mids = [max(0.005, min(0.995, r['mid'])) for r in rs]; s = sum(mids); mids = [m / s for m in mids]
        for r, m in zip(rs, mids):
            qq = max(0.005, min(0.995, r['q']))
            brm += (qq - r['won']) ** 2; brk += (m - r['won']) ** 2
            if r['won']: llm -= math.log(qq); llk -= math.log(m)
        n += 1
    print(f'  per-event log loss: model {llm/n:.3f}  market {llk/n:.3f} | Brier sum/event model {brm/n:.3f} market {brk/n:.3f}')
    # market calibration by Yes ask bin
    print('  market calibration (Yes ask bin: n, mean ask, win rate, model mean q):')
    bins = [(0, .05), (.05, .15), (.15, .3), (.3, .5), (.5, .7), (.7, .85), (.85, .95), (.95, 1.01)]
    for lo, hi in bins:
        sub = [r for r in R if r['yes_ask'] is not None and lo <= r['yes_ask'] < hi]
        if sub: print(f'    {lo:.2f}-{hi:.2f}: n {len(sub):4d} ask {sum(r["yes_ask"] for r in sub)/len(sub):.3f} won {sum(r["won"] for r in sub)/len(sub):.3f} q {sum(r["q"] for r in sub)/len(sub):.3f}  mid {sum(r["mid"] for r in sub)/len(sub):.3f}')
    print('  model calibration (q bin: n, mean q, win rate):')
    for lo, hi in bins:
        sub = [r for r in R if lo <= r['q'] < hi]
        if sub: print(f'    {lo:.2f}-{hi:.2f}: n {len(sub):4d} q {sum(r["q"] for r in sub)/len(sub):.3f} won {sum(r["won"] for r in sub)/len(sub):.3f}')
    for w in [1.0, 0.5, 0.3]:
        for X in [0.02, 0.05, 0.10, 0.15]:
            trades = []
            for r in R:
                qq = w * r['q'] + (1 - w) * r['mid']
                if r['yes_ask'] and 0.01 < r['yes_ask'] < 0.99 and qq - r['yes_ask'] - fee(r['yes_ask']) > X:
                    trades.append(('Y', r['yes_ask'], r['won'] - r['yes_ask'] - fee(r['yes_ask'])))
                if r['no_ask'] and 0.01 < r['no_ask'] < 0.99 and (1 - qq) - r['no_ask'] - fee(r['no_ask']) > X:
                    trades.append(('N', r['no_ask'], (1 - r['won']) - r['no_ask'] - fee(r['no_ask'])))
            if trades:
                pnl = [t[2] for t in trades]; m = sum(pnl) / len(pnl); sd = (sum((x - m) ** 2 for x in pnl) / max(1, len(pnl) - 1)) ** .5
                cost = sum(t[1] for t in trades)
                ny = sum(1 for t in trades if t[0] == 'Y')
                print(f'  rule w={w} X={X}: n {len(trades)} (Yes {ny}, No {len(trades)-ny}) mean pnl/contract {m*100:+.2f}c  se {sd/len(pnl)**.5*100:.2f}c  ROI on cost {sum(pnl)/cost*100:+.1f}%')
