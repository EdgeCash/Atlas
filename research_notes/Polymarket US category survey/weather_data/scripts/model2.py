# variant: gaussian, rolling 30-day station bias, sd = k * max(xnd,1); scored vs market
import json, math, collections, datetime as dt
recs = json.load(open('raw/bt_recs.json'))
resid = {tuple(k.split('|')): v for k, v in json.load(open('raw/resid.json')).items()}
nbs = {tuple(k.split('|')): v for k, v in json.load(open('raw/nbs_txn.json')).items()}
def Phi(x): return 0.5 * (1 + math.erf(x / 2 ** .5))
LEAD = {'T1 D-1 20Z (NBS D-1 18Z)': ('D-1 18Z', -1, 18), 'T2 D 14Z (NBS D 12Z)': ('D 12Z', 0, 12)}
for setup, (lead, dd, rh) in LEAD.items():
    for k in [1.0, 1.3, 1.6]:
        byev = collections.defaultdict(list)
        for r in recs:
            if r['setup'] == setup: byev[(r['station'], r['date'])].append(r)
        llm = llk = 0; n = 0
        for (s, D), rs in byev.items():
            d = dt.date.fromisoformat(D)
            past = [x[2] for x in resid[('high', lead)] if x[0] == s and (d - dt.timedelta(days=30)).isoformat() <= x[1] < D]
            if len(past) < 10: continue
            bias = sum(past) / len(past)
            rt = (d + dt.timedelta(days=dd)).strftime('%Y-%m-%d') + f' {rh:02d}'
            f = nbs[(s, rt, (d + dt.timedelta(days=1)).strftime('%Y-%m-%d') + ' 00')]
            mu = f[0] + bias; sd = k * max(f[1] or 2, 1.0)
            for r in rs:
                if r['won']:
                    lo = -1e9 if r['lo'] < -900 else r['lo'] - 0.5; hi = 1e9 if r['hi'] > 900 else r['hi'] + 0.5
                    q = max(0.005, Phi((hi - mu) / sd) - Phi((lo - mu) / sd))
                    mids = [max(0.005, min(0.995, x['mid'])) for x in rs]; m = max(0.005, min(0.995, r['mid'])) / sum(mids)
                    llm -= math.log(q); llk -= math.log(m); n += 1
        print(setup, 'k', k, 'events', n, 'logloss model %.3f market %.3f' % (llm / n, llk / n))
