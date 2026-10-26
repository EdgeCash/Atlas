import sys, json, os, collections, datetime as dt
sys.path.insert(0, 'scripts')
from obs import LST
def fee(p): return 0.0695 * p * (1 - p)
ev = json.load(open('raw/events.json'))
WIN = [('D-1 (any hour)', -99, 0), ('D 00-09 LST', 0, 9), ('D 09-12', 9, 12), ('D 12-15', 12, 15), ('D 15-18', 15, 18), ('D 18-24', 18, 24)]
BINS = [(0, .03), (.03, .10), (.10, .30), (.30, .50), (.50, .70), (.70, .90), (.90, .95), (.95, .99)]
cell = collections.defaultdict(list)   # (win, bin) -> list of (ask, won, no_pnl)
nev = 0
for e in ev:
    if e['kind'] != 'high': continue
    hs = []
    for b in e['buckets']:
        fn = f"raw/hist60/{b['slug']}.json"
        if not os.path.exists(fn): break
        hs.append(json.load(open(fn)).get('history', []))
    if len(hs) != len(e['buckets']): continue
    nev += 1
    D = dt.date.fromisoformat(e['date']); off = LST[e['station']]
    d0 = dt.datetime.combine(D, dt.time(0), dt.timezone.utc) - dt.timedelta(hours=off)
    for b, h in zip(e['buckets'], hs):
        for x in h:
            t = dt.datetime.fromtimestamp(x['timestamp'], dt.timezone.utc)
            hr = (t - d0).total_seconds() / 3600
            if hr >= 24: continue
            ya, na = x.get('longPrice'), x.get('shortPrice')
            if ya is None or na is None or (1 - na) > ya + 1e-9: continue   # skip crossed / one-sided artefacts
            for name, lo, hi in WIN:
                if lo <= hr < hi:
                    for bl, bh in BINS:
                        if bl <= ya < bh: cell[(name, (bl, bh))].append((ya, b['won'], na))
print('events with full hourly history:', nev)
print('Yes-ask bin | window: n hourly obs, mean ask, win rate, buy-Yes pnl/contract after fee, buy-No pnl after fee')
for bl, bh in BINS:
    for name, _, _ in WIN:
        c = cell[(name, (bl, bh))]
        if len(c) < 10: continue
        m = sum(a for a, w, n in c) / len(c); wr = sum(w for a, w, n in c) / len(c)
        py = sum(w - a - fee(a) for a, w, n in c) / len(c); pn = sum((1 - w) - n - fee(n) for a, w, n in c) / len(c)
        print(f'  {bl:.2f}-{bh:.2f} | {name:15s}: n {len(c):5d} ask {m:.3f} won {wr:.3f}  Yes {py*100:+.2f}c  No {pn*100:+.2f}c')
