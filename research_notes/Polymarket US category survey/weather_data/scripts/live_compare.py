import json, sys, re, csv
sys.path.insert(0, 'scripts')
from model import dist, bucket_probs, fee
CITY = {'nyc':'KNYC','mia':'KMIA','mdw':'KMDW','lax':'KLAX','sfo':'KSFO','phl':'KPHL'}
nbs = {tuple(k.split('|')): v for k, v in json.load(open('raw/nbs_txn.json')).items()}
b = json.load(open(sys.argv[1])); rt = sys.argv[2]; lead = sys.argv[3]
print('book ts', b['ts'], 'NBS run', rt, 'lead', lead)
ev = {}
for slug, v in b['books'].items():
    m = re.match(r'tc-temp-(\w{3})(high|low)-(\d{4}-\d{2}-\d{2})-(.*)f$', slug)
    c, kind, D, bb = m.groups()
    if (mm := re.match(r'lt(\d+)$', bb)): lo, hi = -999, int(mm[1]) - 1
    elif (mm := re.match(r'gte(\d+)lt(\d+)$', bb)): lo, hi = int(mm[1]), int(mm[1]) + 1
    else: lo, hi = int(re.match(r'gte(\d+)$', bb)[1]), 999
    md = v['book'].get('marketData', {})
    bid = float(md['bids'][0]['px']['value']) if md.get('bids') else None
    ask = float(md['offers'][0]['px']['value']) if md.get('offers') else None
    aq = float(md['offers'][0]['qty']) if md.get('offers') else 0
    bq = float(md['bids'][0]['qty']) if md.get('bids') else 0
    ev.setdefault((CITY[c], kind, D), []).append((lo, hi, bid, ask, bq, aq, slug))
rows = []
for (s, kind, D), bs in sorted(ev.items()):
    bs.sort()
    ft = '2026-10-27 00' if kind == 'high' else '2026-10-26 12'
    f = nbs.get((s, rt, ft))
    if not f: print('no nbs', s, kind); continue
    d = dist(kind, lead, s)
    ps = bucket_probs(f[0], d, [(x[0], x[1]) for x in bs])
    mids = [((x[2] or 0) + (x[3] or 1)) / 2 for x in bs]
    print(f'== {s} {kind} {D} NBS txn {f[0]} xnd {f[1]}  sum(ask)={sum(x[3] or 1 for x in bs):.2f}')
    for x, p, mid in zip(bs, ps, mids):
        lo, hi, bid, ask, bq, aq, slug = x
        ey = p - ask - fee(ask) if ask else None
        en = (1 - p) - (1 - bid) - fee(1 - bid) if bid else None
        print(f'   {lo:>4}-{hi:<4} model {p:5.3f} | bid {bid} x{bq:.0f} ask {ask} x{aq:.0f} | EV yes {ey if ey is None else round(ey,3)} EV no {en if en is None else round(en,3)}')
        rows.append(dict(station=s, kind=kind, date=D, lo=lo, hi=hi, model=round(p, 4), bid=bid, ask=ask, bid_qty=bq, ask_qty=aq, ev_yes=ey, ev_no=en, nbs_txn=f[0], nbs_run=rt))
json.dump(rows, open(sys.argv[4], 'w'))
