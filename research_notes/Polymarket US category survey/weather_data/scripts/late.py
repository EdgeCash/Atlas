# per-event snapshot at fixed LST hours on day D, minute data: calibration of high-priced buckets
import sys, json, os, collections, datetime as dt
sys.path.insert(0, 'scripts')
from obs import LST
def fee(p): return 0.0695 * p * (1 - p)
ev = json.load(open('raw/events.json'))
def load(slug):
    fn = f'raw/histmin/{slug}.json'
    if not os.path.exists(fn): return None
    return {t: (l, s) for t, l, s in json.load(open(fn))['h']}
HRS = [11, 13, 15, 17, 19, 21]
cells = collections.defaultdict(list); nev = 0; losers = []
for e in ev:
    if e['kind'] != 'high': continue
    ser = [load(b['slug']) for b in e['buckets']]
    if not all(ser): continue
    nev += 1
    D = dt.date.fromisoformat(e['date']); off = LST[e['station']]
    for h in HRS:
        t = int((dt.datetime.combine(D, dt.time(h), dt.timezone.utc) - dt.timedelta(hours=off)).timestamp())
        for b, s in zip(e['buckets'], ser):
            p = s.get(t)
            if not p or p[0] is None or p[1] is None: continue
            ya, na = p
            if (1 - na) > ya + 1e-9: continue
            for lo, hi in [(0.80, 0.90), (0.90, 0.95), (0.95, 0.97), (0.97, 0.99)]:
                if lo <= ya < hi:
                    cells[(h, lo)].append((ya, b['won']))
                    if not b['won']: losers.append((e['station'], e['date'], h, b['lo'], b['hi'], ya, e['cli']))
print('events', nev)
for lo in [0.80, 0.90, 0.95, 0.97]:
    for h in HRS:
        c = cells[(h, lo)]
        if c: print(f'  ask {lo:.2f}+ at {h:02d} LST: n {len(c):3d} mean ask {sum(a for a,w in c)/len(c):.3f} won {sum(w for a,w in c)}/{len(c)}  buy-Yes pnl {sum(w-a-fee(a) for a,w in c)/len(c)*100:+.2f}c')
print('losers', losers)
