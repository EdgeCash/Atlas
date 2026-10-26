import csv, json, collections, datetime as dt, statistics as st, math
ST = ['KNYC','KMIA','KMDW','KLAX','KSFO','KPHL']
nbs = {}
for s in ST:
    for x in csv.DictReader(open(f'raw/mos/NBS_{s}.csv')):
        if x['txn']:
            nbs[(s, x['runtime'][:13], x['ftime'][:13])] = (float(x['txn']), float(x['xnd']) if x['xnd'] else None)
json.dump({'|'.join(k): v for k, v in nbs.items()}, open('raw/nbs_txn.json', 'w'))
ev = json.load(open('raw/events.json'))
def D(s): return dt.datetime.fromisoformat(s)
LEADS_H = {'D-1 12Z': (-1, 12), 'D-1 18Z': (-1, 18), 'D 00Z': (0, 0), 'D 06Z': (0, 6), 'D 12Z': (0, 12), 'D 18Z': (0, 18)}
res = collections.defaultdict(list)
for e in ev:
    if not isinstance(e['cli'], (int, float)): continue
    d = D(e['date'])
    if e['kind'] == 'high': ft = (d + dt.timedelta(days=1)).strftime('%Y-%m-%d %H')[:11] + '00'
    else: ft = d.strftime('%Y-%m-%d') + ' 12'
    for lab, (dd, hh) in LEADS_H.items():
        if e['kind'] == 'low' and lab in ('D 12Z', 'D 18Z'): continue
        rt = (d + dt.timedelta(days=dd)).strftime('%Y-%m-%d') + f' {hh:02d}'
        f = nbs.get((e['station'], rt, ft))
        if f: res[(e['kind'], lab)].append((e['station'], e['date'], e['cli'] - f[0], f[1]))
out = {}
for k, v in sorted(res.items()):
    r = [x[2] for x in v]; sd = [x[3] for x in v if x[3]]
    z = [x[2] / x[3] for x in v if x[3]]
    print(k, 'n', len(r), 'bias %.2f' % st.mean(r), 'sd %.2f' % st.pstdev(r), 'MAE %.2f' % st.mean(abs(a) for a in r), 'mean xnd %.2f' % st.mean(sd), 'sd(z) %.2f' % st.pstdev(z), '|r|<=1: %.2f' % (sum(abs(a) <= 1 for a in r) / len(r)))
    if k[0] == 'high':
        for s in ST:
            rr = [x[2] for x in v if x[0] == s]
            if rr: print('    ', s, len(rr), 'bias %.2f sd %.2f' % (st.mean(rr), st.pstdev(rr)))
json.dump({'|'.join(k): v for k, v in res.items()}, open('raw/resid.json', 'w'))
