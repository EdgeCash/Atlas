import math, random, statistics as S
v = {2023:[4.791,4.778,4.813,4.790,4.960,5.028,5.102,5.076,5.109,5.226,5.353,5.210],
     2024:[5.030,5.132,5.132,5.236,5.148,5.472,5.497,5.577,5.670,5.588,5.628,5.605],
     2025:[5.545,5.625,5.790,5.801,5.981,6.120,6.254,6.318,6.323,None,6.540,6.687],
     2026:[6.752,6.739,6.701,6.899,6.745,6.825,6.885,6.923,6.792]}
seq = [x for y in sorted(v) for x in v[y]]
r = [math.log(b/a) for a, b in zip(seq, seq[1:]) if a and b]
r26 = [math.log(b/a) for a, b in zip(v[2026], v[2026][1:])]
print('monthly log chg all: mean %.4f sd %.4f n %d | 2026: mean %.4f sd %.4f n %d' % (S.mean(r), S.stdev(r), len(r), S.mean(r26), S.stdev(r26), len(r26)))
# mean reversion check: lag-1 autocorrelation
ac = S.correlation(r[:-1], r[1:]); print('lag-1 autocorr of monthly changes %.2f' % ac)
s0 = 6.792
mk_hi = {7.00:(0.98,0.99),7.10:(0.17,0.19),7.20:(0.20,0.21),7.30:(0.22,0.23),7.40:(0.16,0.17)}
mk_lo = {6.80:(0.99,None),6.70:(0.39,0.40),6.60:(0.29,0.30),6.50:(0.03,0.11),6.40:(0.08,0.09)}
random.seed(1)
for label, mu, sd in [('driftless sd(2026)', 0.0, S.stdev(r26)), ('driftless sd(all)', 0.0, S.stdev(r)), ('drift(all) sd(all)', S.mean(r), S.stdev(r)), ('2026 drift sd(2026)', S.mean(r26), S.stdev(r26))]:
    N = 200000; hi = {k:0 for k in mk_hi}; lo = {k:0 for k in mk_lo}
    for _ in range(N):
        x = s0; mx = s0; mn = s0
        for m in range(3):
            x *= math.exp(random.gauss(mu, sd)); x = round(x, 3); mx = max(mx, x); mn = min(mn, x)
        for k in hi:
            if mx >= k - 1e-9: hi[k] += 1
        for k in lo:
            if mn <= k + 1e-9: lo[k] += 1
    print(label, 'mu %.4f sd %.4f' % (mu, sd))
    print('   HIGH ', '  '.join(f'>={k:.2f}: fair {hi[k]/N:.3f} mkt {mk_hi[k][0]:.2f}/{mk_hi[k][1]:.2f}' for k in sorted(hi)))
    print('   LOW  ', '  '.join(f'<={k:.2f}: fair {lo[k]/N:.3f} mkt {mk_lo[k][0]}/{mk_lo[k][1]}' for k in sorted(lo, reverse=True)))
