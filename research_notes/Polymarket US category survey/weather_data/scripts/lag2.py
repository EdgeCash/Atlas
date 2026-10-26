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
    k = int(t // 60 * 60)
    for i in range(0, 11):
        if k - 60 * i in series: return series[k - 60 * i]
    return None
def ok(p): return p and p[0] is not None and p[1] is not None and (1 - p[1]) <= p[0] + 1e-9
DELAY = 240
kills, locks = [], []
for e in ev:
    if e['kind'] != 'high' or not isinstance(e['cli'], int): continue
    s = e['station']; D = dt.date.fromisoformat(e['date'])
    ser = {b['slug']: load_min(b['slug']) for b in e['buckets']}
    if not all(ser.values()): continue
    off = LST[s]
    start = dt.datetime.combine(D, dt.time(0), dt.timezone.utc) - dt.timedelta(hours=off)
    end = start + dt.timedelta(days=1)
    ob = [o for o in obs_for(s) if start <= o['t'] < end]
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
        t_obs = first_above[b['slug']].timestamp(); srs = ser[b['slug']]
        pre = at(srs, t_obs - 1800)
        if not pre or pre[0] is None or pre[1] is None: continue
        pre_mid = (pre[0] + 1 - pre[1]) / 2
        if pre_mid < 0.05: continue
        p0 = at(srs, t_obs + DELAY)
        if not p0: continue
        # minutes until implied Yes bid (1-short) <= 0.02
        tt = None
        for k in range(-60, 12 * 60):
            q = srs.get(int((t_obs + DELAY) // 60 * 60) + 60 * k)
            if q and q[1] is not None and q[1] >= 0.98:
                if k >= 0 or tt is None: pass
                tt = k; break
        kills.append(dict(station=s, date=e['date'], bucket=f"{b['lo']}-{b['hi']}", won=b['won'], t_obs=first_above[b['slug']].isoformat(), lst=(first_above[b['slug']] + dt.timedelta(hours=off)).strftime('%H:%M'),
                          pre_mid=round(pre_mid, 3), no_ask=p0[1], yes_ask=p0[0], quote_ok=bool(ok(p0)), min_to_098=tt,
                          no_ask_15=(at(srs, t_obs + DELAY + 900) or [None, None])[1], no_ask_60=(at(srs, t_obs + DELAY + 3600) or [None, None])[1]))
    # lock at 00:05Z D+1 using 6h max groups
    tl = dt.datetime.combine(D + dt.timedelta(days=1), dt.time(0, 5), dt.timezone.utc)
    allob = [o for o in parse(s) if start <= o['t'] <= tl]
    if not allob: continue
    M = max([o['tf'] for o in obs_for(s) if start <= o['t'] <= tl] + [o['mx6'] for o in allob if o['mx6'] is not None and o['t'] >= start + dt.timedelta(hours=6)])
    cur = [o['tf'] for o in obs_for(s) if o['t'] <= tl][-1]
    have00 = any(o['mx6'] is not None and o['t'] >= tl - dt.timedelta(minutes=20) for o in allob)
    for b in e['buckets']:
        if b['lo'] <= M <= b['hi']:
            p = at(ser[b['slug']], tl.timestamp() + 300)
            first95 = None
            for k in range(-18 * 60, 9 * 60):
                q = ser[b['slug']].get(int(tl.timestamp() // 60 * 60) + 60 * k)
                if q and q[0] is not None and q[0] >= 0.95 and (1 - q[1]) >= 0.90: first95 = k; break
            locks.append(dict(station=s, date=e['date'], M=M, cli=e['cli'], cur=cur, drop=M - cur, have00=have00, bucket=f"{b['lo']}-{b['hi']}", won=b['won'], yes_ask=p and p[0], no_ask=p and p[1], quote_ok=bool(ok(p)), min_first95_vs_lock=first95))
json.dump(dict(kills=kills, locks=locks), open('raw/lag2.json', 'w'))
K = kills
print('MARGINAL lower-bound kills (bucket mid>=5c 30 min before crossing):', len(K), 'won:', sum(k['won'] for k in K))
for thr in [0.90, 0.95, 0.97, 0.98]:
    sub = [k for k in K if k['no_ask'] is not None and k['no_ask'] <= thr]
    sub_ok = [k for k in sub if k['quote_ok']]
    pnl = sum((1 - k['won']) - k['no_ask'] - fee(k['no_ask']) for k in sub_ok)
    print(f'  No ask <= {thr} at obs+4min: {len(sub)} ({len(sub)/max(1,len(K)):.0%}), uncrossed {len(sub_ok)}, mean edge {pnl/max(1,len(sub_ok))*100:.2f}c')
for lab in ['no_ask', 'no_ask_15', 'no_ask_60']:
    print(' ', lab, 'distribution', sorted(collections.Counter(k[lab] for k in K if k[lab] is not None).items()))
ms = sorted(k['min_to_098'] for k in K if k['min_to_098'] is not None)
print('  minutes from obs+4min to No ask>=0.98 (negative = market moved before obs was public): quartiles', [ms[int(len(ms)*q)] for q in (0.1, .25, .5, .75, .9)] if ms else None, 'n', len(ms))
L = locks
print('LOCK at 00:05Z (true max from 6h groups), events:', len(L))
for cond in [lambda l: True, lambda l: l['drop'] >= 3, lambda l: l['drop'] >= 5]:
    sub = [l for l in L if cond(l)]
    print('  n', len(sub), 'bucket(M) won', sum(l['won'] for l in sub), ' M==CLI', sum(l['M'] == l['cli'] for l in sub))
    av = [l for l in sub if l['yes_ask'] is not None and l['yes_ask'] < 0.99 and l['quote_ok']]
    print('    Yes ask <0.99 & uncrossed at lock+5:', len(av), 'asks', sorted(collections.Counter(l['yes_ask'] for l in av).items()), 'pnl/contract', round(sum(l['won'] - l['yes_ask'] - fee(l['yes_ask']) for l in av) / max(1, len(av)) * 100, 2), 'c')
f95 = sorted(l['min_first95_vs_lock'] for l in L if l['min_first95_vs_lock'] is not None)
print('  minutes (rel. to 00:05Z) when winner first Yes ask>=0.95: quartiles', [f95[int(len(f95)*q)] for q in (0.1, .25, .5, .75, .9)] if f95 else None, 'n', len(f95))
for l in L:
    if l['M'] != l['cli'] or not l['won']: print('   miss', l)
