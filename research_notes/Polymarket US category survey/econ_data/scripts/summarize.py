import json, sys
ev=json.load(open('raw/econ_events.json')); books=json.load(open(sys.argv[1]))
MIN=5  # shares to count as real
rows=[]
for e in ev:
    if e['slug'].startswith(('usgas','usbeef')): continue
    for m in sorted(e['markets'],key=lambda m:m.get('sortOrder',0)):
        b=books.get(m['slug'],{}).get('marketData',{})
        bids=[(float(x['px']['value']),float(x['qty'])) for x in b.get('bids',[])]
        offs=[(float(x['px']['value']),float(x['qty'])) for x in b.get('offers',[])]
        bids.sort(reverse=True); offs.sort()
        rb=[x for x in bids if x[1]>=MIN]; ro=[x for x in offs if x[1]>=MIN]
        st=b.get('stats',{})
        bb=rb[0] if rb else (None,0); ba=ro[0] if ro else (None,0)
        rows.append(dict(event=e['slug'],slug=m['slug'],title=m.get('title') or m.get('titleShort'),tick=m.get('orderPriceMinTickSize'),fee=m.get('feeCoefficient'),
          bid=bb[0],bidq=bb[1],ask=ba[0],askq=ba[1],rawbid=bids[0][0] if bids else None,rawask=offs[0][0] if offs else None,
          traded=float(st.get('sharesTraded') or 0),notional=float((st.get('notionalTraded') or {}).get('value') or 0),oi=float(st.get('openInterest') or 0),
          last=(st.get('lastTradePx') or {}).get('value'),lastt=st.get('lastTradeSetTime'),fetched=books.get(m['slug'],{}).get('_fetched'),
          end=m.get('endDate'),gst=m.get('gameStartTime')))
json.dump(rows,open(sys.argv[2],'w'),indent=0)
cur=None
for r in rows:
    if r['event']!=cur:
        cur=r['event']; print('\n##',cur)
    f=lambda x:'-' if x is None else f'{x:.3f}'
    print(f"{r['title'][:34]:34s} b {f(r['bid'])}x{r['bidq']:<9.0f} a {f(r['ask'])}x{r['askq']:<9.0f} raw {f(r['rawbid'])}/{f(r['rawask'])} tick {r['tick']} fee {r['fee']} trd {r['traded']:.0f} \${r['notional']:.0f} oi {r['oi']:.0f} last {r['last']} {str(r['lastt'])[:16]}")
