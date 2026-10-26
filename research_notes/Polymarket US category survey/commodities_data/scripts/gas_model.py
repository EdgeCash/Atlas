import json, math, datetime, statistics as S, random
A = json.load(open('raw/aaa_daily.json')); Y = json.load(open('ext/yahoo_daily.json'))
days = sorted(A); r = [A[d] for d in days]
# RBOB forward-filled to calendar days, lagged by one day (AAA for date D reflects prior-day station prices)
rb = {}; last = None
d0 = datetime.date.fromisoformat(days[0]) - datetime.timedelta(days=10)
for i in range((datetime.date.fromisoformat(days[-1]) - d0).days + 1):
    d = (d0 + datetime.timedelta(days=i)).isoformat()
    if d in Y['RB=F']: last = Y['RB=F'][d]
    rb[d] = last
def prev(d, k=1): return (datetime.date.fromisoformat(d) - datetime.timedelta(days=k)).isoformat()
print('min since Sep 9 on', [d for d in days if d >= '2026-09-09' and A[d] == min(A[x] for x in days if x >= '2026-09-09')])
# ---- daily change persistence
dl = [b - a for a, b in zip(r, r[1:])]
print('daily change: mean %.4f sd %.4f; lag-1 autocorr %.2f; lag-2 %.2f' % (S.mean(dl), S.stdev(dl), S.correlation(dl[:-1], dl[1:]), S.correlation(dl[:-2], dl[2:])))
# OLS helper
def ols(X, y):
    k = len(X[0]); XtX = [[sum(x[i]*x[j] for x in X) for j in range(k)] for i in range(k)]; Xty = [sum(x[i]*yy for x, yy in zip(X, y)) for i in range(k)]
    A_ = [XtX[i] + [Xty[i]] for i in range(k)]
    for i in range(k):
        p = A_[i][i]; A_[i] = [v/p for v in A_[i]]
        for j in range(k):
            if j != i:
                f = A_[j][i]; A_[j] = [a - f*b for a, b in zip(A_[j], A_[i])]
    return [A_[i][k] for i in range(k)]
# next-day nowcast models, walk-forward from day 60
rows = []
for i in range(8, len(days)):
    d = days[i]
    rows.append(dict(d=d, y=r[i]-r[i-1], d1=r[i-1]-r[i-2], d2=r[i-2]-r[i-3], gap=(rb[prev(d,1)] + 0) - r[i-1], drb=rb[prev(d,1)] - rb[prev(d,8)]))
res = {'naive0': [], 'ar1': [], 'ar1+gap': []}
for j in range(60, len(rows)):
    tr = rows[:j]; te = rows[j]
    res['naive0'].append(te['y'])
    b = ols([[1, x['d1']] for x in tr], [x['y'] for x in tr]); res['ar1'].append(te['y'] - (b[0] + b[1]*te['d1']))
    b2 = ols([[1, x['d1'], x['d2'], x['gap'], x['drb']] for x in tr], [x['y'] for x in tr]); res['ar1+gap'].append(te['y'] - (b2[0] + b2[1]*te['d1'] + b2[2]*te['d2'] + b2[3]*te['gap'] + b2[4]*te['drb']))
for k, v in res.items(): print('walk-forward next-day error %-8s n %d RMSE %.4f  MAE %.4f' % (k, len(v), math.sqrt(S.mean(x*x for x in v)), S.mean(abs(x) for x in v)))
bfull = ols([[1, x['d1'], x['d2'], x['gap'], x['drb']] for x in rows], [x['y'] for x in rows]); print('full-sample coefs [c, d1, d2, gap, dRB7]:', [round(x, 4) for x in bfull])
sd_ar = math.sqrt(S.mean(x*x for x in res['ar1+gap']))
# forecast for Oct 26
t = dict(d1=r[-1]-r[-2], d2=r[-2]-r[-3], gap=rb[days[-1]] - r[-1], drb=rb[days[-1]] - rb[prev(days[-1], 7)])
f = bfull[0] + bfull[1]*t['d1'] + bfull[2]*t['d2'] + bfull[3]*t['gap'] + bfull[4]*t['drb']
mu = r[-1] + f
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
print('Oct 26 forecast: %.4f (today %.4f, d1 %.4f) sd %.4f' % (mu, r[-1], t['d1'], sd_ar))
for K in [4.2700, 4.2750, 4.2800, 4.2850, 4.2900, 4.2950, 4.3000]:
    print('   P(>%.4f) = %.3f' % (K, 1 - Phi((K - mu)/sd_ar)))
json.dump(dict(bfull=bfull, sd=sd_ar, mu=mu), open('raw/gas_nowcast.json', 'w'))
# ---- partial-adjustment model for year-end high/low ladders: dr_t = k*(rb_{t-1} + s - r_{t-1}) (asymmetric k up/down)
X = []; yv = []
for i in range(1, len(days)):
    X.append([1, rb[prev(days[i], 1)], r[i-1]]); yv.append(r[i] - r[i-1])
b = ols(X, yv); k = -b[2]; s = b[0]/k if k else 0; bb = b[1]
print('partial adjustment: dr = %.4f + %.4f*RB(t-1) - %.4f*r(t-1)  -> implied pass-through %.2f, spread %.3f, half-life %.1f days' % (b[0], bb, k, bb/k, s, math.log(2)/k))
resid = [yy - sum(c*x for c, x in zip(b, xx)) for xx, yy in zip(X, yv)]; rs = S.stdev(resid)
print('resid sd %.4f' % rs)
# Monte Carlo to Dec 31 with RBOB GBM vol from OVX-ish levels
H = (datetime.date(2026, 12, 31) - datetime.date(2026, 10, 25)).days
hiK = [4.60, 4.80, 5.00, 5.20, 5.40, 5.60]; loK = [4.00, 3.80, 3.60, 3.40, 3.20, 3.00]
random.seed(7)
for vol in [0.35, 0.50, 0.60]:
    sd = vol/math.sqrt(365); N = 40000; hi = [0]*len(hiK); lo = [0]*len(loK)
    for _ in range(N):
        R = r[-1]; P = rb[days[-1]]; mx = R; mn = R
        for _d in range(H):
            R = R + b[0] + bb*P - k*R + random.gauss(0, rs)
            P *= math.exp(random.gauss(-0.5*sd*sd, sd))
            mx = max(mx, R); mn = min(mn, R)
        for i, K in enumerate(hiK): hi[i] += mx > K
        for i, K in enumerate(loK): lo[i] += mn < K
    print('RBOB vol %.2f:' % vol, 'HIGH ' + ' '.join('>%.2f %.3f' % (K, h/N) for K, h in zip(hiK, hi)), '| LOW ' + ' '.join('<%.2f %.3f' % (K, l/N) for K, l in zip(loK, lo)))
