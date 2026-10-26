import sys, json, collections, re, os, datetime as dt, statistics as stt
sys.path.insert(0, 'scripts')
from obs import parse, LST
def fee(p): return 0.0695 * p * (1 - p)
ev = json.load(open('raw/events.json'))
OBS = {}
def obs_for(s):
    if s not in OBS:
        o = [x for x in parse(s) if re.search(r'\bT[01]\d{3}[01]\d{3}\b', x['metar'])]
        o.sort(key=lambda x: x['t']); OBS[s] = o
    return OBS[s]
def load_min(slug):
    fn = f'raw/histmin/{slug}.json'
    if not os.path.exists(fn): return None
    d = json.load(open(fn)); return {t: (l, sh) for t, l, sh in d['h']} if d['h'] else None
def at(series, t):
    """price at minute t (UTC epoch) - carry back up to 10 min"""
    k = int(t // 60 * 60)
    for i in range(0, 11):
        if k - 60 * i in series: return series[k - 60 * i]
    return None
DELAY = 4 * 60   # METAR dissemination delay assumed (s)
kill = []        # lower-bound kills
lock = []        # 00Z lock events
for e in ev:
    if e['kind'] != 'high' or not isinstance(e['cli'], int): continue
    s = e['station']; D = dt.date.fromisoformat(e['date'])
    ser = {b['slug']: load_min(b['slug']) for b in e['buckets']}
    if not all(ser.values()): continue
    off = LST[s]
    start = dt.datetime.combine(D, dt.time(0), dt.timezone.utc) - dt.timedelta(hours=off)
    end = start + dt.timedelta(days=1)
    ob = [o for o in obs_for(s) if start <= o['t'] < end]
    # spike filter: accept obs if within 3F of previous obs
    run = -999; prev = None; first_above = {}
    for o in ob:
        v = o['tf']
        if prev is not None and v - prev > 3: prev = v; continue
        prev = v
        if v > run:
            run = v
            for b in e['buckets']:
                if b['hi'] < run and b['slug'] not in first_above: first_above[b['slug']] = o['t']
    for b in e['buckets']:
        if b['slug'] not in first_above: continue
        t0 = first_above[b['slug']].timestamp() + DELAY
        srs = ser[b['slug']]
        p = at(srs, t0)
        if p is None: continue
        no_ask = p[1]
        # minutes until No ask >= 0.99 (Yes bid <= 0.01)
        tt = None
        for k in range(0, 12 * 60):
            q = srs.get(int(t0 // 60 * 60) + 60 * k)
            if q and q[1] is not None and q[1] >= 0.99: tt = k; break
        # first time market No ask >= 0.97, measured from obs
        kill.append(dict(station=s, date=e['date'], lo=b['lo'], hi=b['hi'], won=b['won'], t_obs=first_above[b['slug']].isoformat(), no_ask=no_ask, yes_ask=p[0], min_to_099=tt,
                         lst_hour=(first_above[b['slug']] + dt.timedelta(hours=off)).hour))
json.dump(kill, open('raw/kill.json', 'w'))
k = kill
print('lower-bound kills', len(k), 'won (should be 0):', sum(x['won'] for x in k))
for thr in [0.90, 0.95, 0.97, 0.98]:
    sub = [x for x in k if x['no_ask'] is not None and x['no_ask'] <= thr]
    pnl = sum((1 - x['won']) - x['no_ask'] - fee(x['no_ask']) for x in sub)
    print(f' No ask <= {thr} at obs+4min: {len(sub)} ({len(sub)/len(k):.1%}); pnl/contract sum {pnl:.2f}; mean edge {pnl/max(1,len(sub))*100:.2f}c')
ms = [x['min_to_099'] for x in k if x['min_to_099'] is not None]
print(' minutes from obs+4 to No ask>=0.99: median', stt.median(ms) if ms else None, 'p75', sorted(ms)[3*len(ms)//4] if ms else None, 'p90', sorted(ms)[9*len(ms)//10] if ms else None, 'already at kill', sum(1 for m in ms if m == 0), 'of', len(k))
print(' no_ask distribution at kill:', collections.Counter(round(x['no_ask'], 2) if x['no_ask'] is not None else None for x in k).most_common(15))
