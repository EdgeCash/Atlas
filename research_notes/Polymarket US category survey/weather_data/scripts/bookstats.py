import json, collections, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
print(a['ts'], b['ts'])
def tb(m):
    return ((m.get('bids') or [{}])[0].get('px', {}).get('value'), (m.get('offers') or [{}])[0].get('px', {}).get('value'))
sizes = collections.Counter(); chg = 0; n = 0; spreads = []; topdollars = []; dep5 = []
for s in b['books']:
    A = a['books'][s]['book'].get('marketData', {}); B = b['books'][s]['book'].get('marketData', {})
    for side in ('bids', 'offers'):
        for l in B.get(side, []): sizes[round(float(l['qty']))] += 1
    n += 1; chg += tb(A) != tb(B)
    if B.get('bids') and B.get('offers'):
        bb, aa = float(B['bids'][0]['px']['value']), float(B['offers'][0]['px']['value'])
        if 0.05 < (bb + aa) / 2 < 0.95:
            spreads.append(round(aa - bb, 2)); topdollars.append(float(B['offers'][0]['qty']) * aa)
            dep5.append(sum(float(l['qty']) * float(l['px']['value']) for l in B['offers'] if float(l['px']['value']) <= aa + 0.05))
print('markets', n, 'top-of-book changed between snapshots', chg)
print('most common resting sizes', sizes.most_common(15))
for v in (spreads, topdollars, dep5): v.sort()
q = lambda v, p: v[int(p * (len(v) - 1))]
print('two-sided 5-95c markets', len(spreads), 'spread median', q(spreads, .5), 'p90', q(spreads, .9), '| top-ask $ median', round(q(topdollars, .5)), 'p25', round(q(topdollars, .25)), '| $ within 5c of ask median', round(q(dep5, .5)), 'p25', round(q(dep5, .25)))
