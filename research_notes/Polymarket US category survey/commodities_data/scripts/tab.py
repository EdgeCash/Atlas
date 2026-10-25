import json,sys
s=json.load(open(sys.argv[1]))
def f(x): return float(x['value']) if x else None
for k,v in sorted(s.items(), key=lambda kv:(kv[1]['event'],kv[0])):
    b=(v['bbo'] or {}).get('marketData',{}); bk=(v['book'] or {}).get('marketData',{})
    bids=[(float(l['px']['value']),float(l['qty'])) for l in bk.get('bids',[])]
    offs=[(float(l['px']['value']),float(l['qty'])) for l in bk.get('offers',[])]
    bb=bids[0] if bids else (None,0); ba=offs[0] if offs else (None,0)
    # $ notional within 3c of top
    bd=sum(p*q for p,q in bids if bb[0] and p>=bb[0]-0.03); ad=sum(p*q for p,q in offs if ba[0] and p<=ba[0]+0.03)
    print(f"{k[-34:]:34s} bid {bb[0]} x{bb[1]:.0f} ask {ba[0]} x{ba[1]:.0f} | $bid3c {bd:7.0f} $ask3c {ad:7.0f} | traded {float(b.get('sharesTraded') or 0):9.0f} OI {float(b.get('openInterest') or 0):8.0f} last {f(b.get('lastTradePx'))} | {v['t'][11:19]} age {v['bbo_age']}")
