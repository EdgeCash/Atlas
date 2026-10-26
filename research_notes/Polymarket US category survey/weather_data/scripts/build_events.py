import json, re, collections
CITY = {'nyc':'KNYC','mia':'KMIA','mdw':'KMDW','lax':'KLAX','sfo':'KSFO','phl':'KPHL'}
rows = json.load(open('raw/closed_markets.json'))
cli = {}
for s in set(CITY.values()):
    for r in json.load(open(f'raw/cli/{s}.json'))['results']:
        cli[(s, r['valid'])] = r
ev = collections.defaultdict(list)
for r in rows:
    m = re.match(r'tc-temp-(\w{3})(high|low)-(\d{4}-\d{2}-\d{2})-(.*)f$', r['slug'])
    if not m: continue
    c, kind, D, b = m.groups()
    if (mm := re.match(r'lt(\d+)$', b)): lo, hi = -999, int(mm[1]) - 1
    elif (mm := re.match(r'gte(\d+)lt(\d+)$', b)): lo, hi = int(mm[1]), int(mm[1]) + 1
    elif (mm := re.match(r'gte(\d+)$', b)): lo, hi = int(mm[1]), 999
    else: print('??', r['slug']); continue
    if mm and b.startswith('gte') and 'lt' in b and int(mm[2]) != int(mm[1]) + 1: print('width', r['slug'])
    ev[(CITY[c], kind, D)].append(dict(slug=r['slug'], lo=lo, hi=hi, won=int(r['outcome'][0] == '1'), mend=r['mend']))
out = []; bad = 0
for (s, kind, D), bs in sorted(ev.items()):
    bs.sort(key=lambda x: x['lo'])
    c = cli.get((s, D))
    v = None if not c else c['high' if kind == 'high' else 'low']
    w = [b for b in bs if b['won']]
    ok = None
    if isinstance(v, (int, float)) and len(w) == 1: ok = w[0]['lo'] <= v <= w[0]['hi']
    if ok is False: bad += 1; print('MISMATCH', s, kind, D, v, [(b['lo'], b['hi']) for b in w], c.get('product'))
    out.append(dict(station=s, kind=kind, date=D, cli=v, cli_product=c and c.get('product'), nwin=len(w), buckets=bs))
json.dump(out, open('raw/events.json', 'w'))
print(len(out), 'events; mismatches', bad, collections.Counter(e['nwin'] for e in out), collections.Counter(len(e['buckets']) for e in out))
