import math, random, json
random.seed(11)
r0 = 4.2892; P0 = 3.1165; H = 67
hiK = [4.60, 4.80, 5.00, 5.20, 5.40, 5.60]; loK = [4.00, 3.80, 3.60, 3.40, 3.20, 3.00]
res = {}
for spread in [0.95, 1.00, 1.10]:
    for vol in [0.40, 0.55]:
        k = math.log(2)/10; sd = vol/math.sqrt(365); N = 30000; hi = [0]*6; lo = [0]*6
        for _ in range(N):
            R = r0; P = P0; mx = R; mn = R
            for d in range(H):
                P *= math.exp(random.gauss(-0.5*sd*sd, sd))
                R += k*(P + spread - R) + random.gauss(0, 0.008)
                mx = max(mx, R); mn = min(mn, R)
            for i, K in enumerate(hiK): hi[i] += mx > K
            for i, K in enumerate(loK): lo[i] += mn < K
        res[f'{spread}/{vol}'] = ([h/N for h in hi], [l/N for l in lo])
        print(f'spread {spread:.2f} vol {vol:.2f} | HIGH ' + ' '.join(f'>{K:.2f} {h/N:.2f}' for K, h in zip(hiK, hi)) + ' | LOW ' + ' '.join(f'<{K:.2f} {l/N:.2f}' for K, l in zip(loK, lo)))
json.dump(res, open('raw/gas_year_alt.json', 'w'))
