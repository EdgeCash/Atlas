import json, sys, re
s = json.load(open(sys.argv[1]))
def fee(p): return 0.0695*p*(1-p)
def lv(k, side, minq):
    bk = (s[k]['book'] or {}).get('marketData', {}); L = bk.get('bids' if side == 'b' else 'offers', [])
    L = [(float(l['px']['value']), float(l['qty'])) for l in L]
    L = [x for x in L if x[1] >= minq]
    return L[0] if L else (None, 0)
fams = {}
for k, v in s.items():
    m = re.search(r'-(gt|gte|lt|lte)(\d)pt(\d+)$', k)
    if not m: continue
    K = float(m[2] + '.' + m[3]); fams.setdefault(v['event'], []).append((K, m[1], k))
for ev, L in sorted(fams.items()):
    L.sort()
    up = L[0][1] in ('gt', 'gte')   # P decreasing in K for 'above'; increasing for 'below'
    print('==', ev, 'above' if up else 'below', 'ladder,', len(L), 'strikes')
    for minq in [0.01, 1.0]:
        q = [(K, lv(k, 'b', minq), lv(k, 'a', minq), k) for K, _, k in L]
        viol = []
        # subset relation: for 'above', event(K2>K1) subset of event(K1): need bid(K2) <= ask(K1)
        for i in range(len(q)):
            for j in range(len(q)):
                Ki, bi, ai, _ = q[i]; Kj, bj, aj, _ = q[j]
                sub = (Kj > Ki) if up else (Kj < Ki)   # j's event is a subset of i's
                if sub and bj[0] is not None and ai[0] is not None and bj[0] > ai[0]:
                    net = bj[0] - ai[0] - fee(bj[0]) - fee(ai[0])
                    viol.append(f'buy {Ki} @{ai[0]} x{ai[1]:.1f} / sell {Kj} @{bj[0]} x{bj[1]:.1f}: gross {bj[0]-ai[0]:.2f} net {net:+.3f} size {min(ai[1], bj[1]):.1f}')
        mids = [((b[0] or 0) + (a[0] or 1))/2 for K, b, a, _ in q]
        print(f'  min qty {minq}: top quotes ' + ' '.join(f'{K}:{b[0]}/{a[0]}' for K, b, a, _ in q))
        for v_ in viol: print('    VIOLATION', v_)
