import json, collections, math
def fee(p): return 0.0695 * p * (1 - p)
recs = json.load(open('raw/bt_recs.json'))
RULES = {
 'buy No on favourite (Yes ask 0.50-0.95)': lambda r: 0.50 <= r['yes_ask'] < 0.95 and r['no_ask'] and r['no_ask'] < 0.99 and (1 - r['no_ask']) <= r['yes_ask'],
 'buy Yes on favourite (Yes ask 0.50-0.95)': lambda r: 0.50 <= r['yes_ask'] < 0.95,
 'buy No on longshot (Yes ask 0.05-0.15)': lambda r: 0.05 <= r['yes_ask'] < 0.15 and r['no_ask'] and r['no_ask'] < 0.99 and (1 - r['no_ask']) <= r['yes_ask'],
 'buy No on longshot (Yes ask 0.02-0.05)': lambda r: 0.02 <= r['yes_ask'] < 0.05 and r['no_ask'] and r['no_ask'] < 0.99 and (1 - r['no_ask']) <= r['yes_ask'],
}
for setup in sorted({r['setup'] for r in recs}):
    print('==', setup)
    for name, f in RULES.items():
        side = 'No' if 'No' in name.split(' on ')[0] else 'Yes'
        byev = collections.defaultdict(list)
        for r in recs:
            if r['setup'] == setup and r['yes_ask'] is not None and f(r):
                pr = r['no_ask'] if side == 'No' else r['yes_ask']
                won = (1 - r['won']) if side == 'No' else r['won']
                byev[(r['station'], r['date'])].append(won - pr - fee(pr))
        ev = [sum(v) / len(v) for v in byev.values()]
        allp = [x for v in byev.values() for x in v]
        if not ev: continue
        m = sum(allp) / len(allp); me = sum(ev) / len(ev); sd = (sum((x - me) ** 2 for x in ev) / max(1, len(ev) - 1)) ** .5
        print(f'  {name:45s} contracts {len(allp):4d} events {len(ev):4d}  mean pnl {m*100:+.2f}c/contract  (event-mean {me*100:+.2f}c, event-clustered se {sd/len(ev)**.5*100:.2f}c)')
