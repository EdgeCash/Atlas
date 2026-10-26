import json, sys, time, datetime
sys.path.insert(0, sys.argv[1]); import gw
com = json.load(open(sys.argv[2]))
out = {}
for e in com:
    for m in e['markets']:
        s = m['slug']
        b, h = gw.get(f'https://gateway.polymarket.us/v1/markets/{s}/bbo')
        k, h2 = gw.get(f'https://gateway.polymarket.us/v1/markets/{s}/book')
        out[s] = {'event': e['slug'], 't': datetime.datetime.utcnow().isoformat()+'Z', 'bbo': b, 'book': k, 'bbo_age': h.get('Age'), 'cf': h.get('CF-Cache-Status') or h.get('Cf-Cache-Status')}
json.dump(out, open(sys.argv[3], 'w'))
print(len(out))
