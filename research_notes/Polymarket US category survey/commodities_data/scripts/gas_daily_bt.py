import json, math, datetime, statistics as S
exec(open('scripts/gas_model.py').read().split('# next-day nowcast models')[0])
d = json.load(open('raw/gas_hist.json'))
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def fee(p): return 0.0695*p*(1-p)
rows = []
for i in range(8, len(days)):
    dd = days[i]; rows.append(dict(d=dd, y=r[i]-r[i-1], d1=r[i-1]-r[i-2], d2=r[i-2]-r[i-3], gap=rb[prev(dd,1)]-r[i-1], drb=rb[prev(dd,1)]-rb[prev(dd,8)]))
tot = []
for D in ['2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25']:
    j = [x['d'] for x in rows].index(D); tr = rows[:j]; te = rows[j]
    b = ols([[1,x['d1'],x['d2'],x['gap'],x['drb']] for x in tr], [x['y'] for x in tr])
    res = [x['y'] - (b[0]+b[1]*x['d1']+b[2]*x['d2']+b[3]*x['gap']+b[4]*x['drb']) for x in tr[-120:]]
    sd = math.sqrt(S.mean(e*e for e in res)); mu = A[prev(D)] + b[0]+b[1]*te['d1']+b[2]*te['d2']+b[3]*te['gap']+b[4]*te['drb']
    print(f'{D}: prior {A[prev(D)]:.4f} forecast {mu:.4f} sd {sd:.4f} actual {A[D]:.4f} (z {(A[D]-mu)/sd:+.2f})')
    for k, v in sorted(d.items()):
        if v['event'] != 'usgas-day-'+D: continue
        K = int(k.split('gt4pt')[1])/10000 + 4
        h = [x for x in v['hist'] if x['timestamp'] <= v['ee']-120]
        if not h: continue
        q = max(h, key=lambda x: x['timestamp']); ask = q['longPrice']; bid = round(1-q['shortPrice'], 2)
        p = 1-Phi((K-mu)/sd); y = v['settle']['settlement']
        sig = ''
        if 0 < ask < 1 and p-ask-fee(ask) > 0.03: sig = f'BUY yes@{ask} pnl {y-ask-fee(ask):+.2f}'; tot.append(y-ask-fee(ask))
        elif 0 < bid < 1 and bid-p-fee(bid) > 0.03: sig = f'SELL yes@{bid} pnl {bid-y-fee(bid):+.2f}'; tot.append(bid-y-fee(bid))
        print(f'   >{K:.4f} fair {p:.2f} bid {bid:.2f} ask {ask:.2f} settle {y} {sig}')
print('signals', len(tot), 'mean pnl/contract %+.3f' % S.mean(tot), 'wins', sum(1 for x in tot if x > 0))
