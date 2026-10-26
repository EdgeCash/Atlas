import sys, json, os, re, datetime as dt, collections
sys.path.insert(0, 'scripts')
from obs import parse, LST
def fee(p): return 0.0695 * p * (1 - p)
ev = json.load(open('raw/events.json')); L = json.load(open('raw/lag2.json'))
OB = {}
def load(slug):
    return {t: (l, s) for t, l, s in json.load(open(f'raw/histmin/{slug}.json'))['h']}
hits = []
# lower-bound kills: scan after obs+4min
kills = {(k['station'], k['date'], k['bucket']): k for k in L['kills']}
evmap = {(e['station'], e['date']): e for e in ev if e['kind'] == 'high'}
allk = []
for e in evmap.values():
    if not os.path.exists(f"raw/histmin/{e['buckets'][0]['slug']}.json"): continue
for k in L['kills']:
    e = evmap[(k['station'], k['date'])]
    b = [b for b in e['buckets'] if f"{b['lo']}-{b['hi']}" == k['bucket']][0]
    s = load(b['slug']); t0 = dt.datetime.fromisoformat(k['t_obs']).timestamp() + 240
    best = None; mins = 0
    for t, (l, sh) in sorted(s.items()):
        if t < t0 or l is None or sh is None: continue
        if (1 - sh) <= l + 1e-9 and sh <= 0.90:
            mins += 1
            if best is None or sh < best: best = sh
    if best is not None: hits.append(('kill-No', k['station'], k['date'], k['bucket'], best, mins, b['won']))
for l in L['locks']:
    if not (l['have00'] and l['drop'] >= 3): continue
    e = evmap[(l['station'], l['date'])]
    b = [b for b in e['buckets'] if f"{b['lo']}-{b['hi']}" == l['bucket']][0]
    s = load(b['slug']); t0 = dt.datetime.combine(dt.date.fromisoformat(l['date']) + dt.timedelta(days=1), dt.time(0, 5), dt.timezone.utc).timestamp()
    best = None; mins = 0
    for t, (ya, sh) in sorted(s.items()):
        if t < t0 or ya is None or sh is None: continue
        if (1 - sh) <= ya + 1e-9 and ya <= 0.90:
            mins += 1
            if best is None or ya < best: best = ya
    if best is not None: hits.append(('lock-Yes', l['station'], l['date'], l['bucket'], best, mins, l['won']))
for h in sorted(hits, key=lambda x: x[2]): print(h)
print('distinct event-days', len({(h[1], h[2]) for h in hits}), 'distinct dates', sorted({h[2] for h in hits}))
print('lock events eligible', sum(1 for l in L['locks'] if l['have00'] and l['drop'] >= 3), 'marginal kills', len(L['kills']))
