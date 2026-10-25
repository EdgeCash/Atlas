import json,time,urllib.request,urllib.error,datetime as dt,collections
H=json.load(open('raw/closed_hist_1m.json'))
res={}
for s,v in H.items():
    for a in range(5):
        try:
            d=json.load(urllib.request.urlopen(f"https://gateway.polymarket.us/v1/markets/{s}/book",timeout=30)); break
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(a+1)); continue
            d={}; break
    md=d.get('marketData',{}); st=md.get('stats',{})
    res[s]={'event':v['event'],'T':v['T'],'title':v['title'],'state':md.get('state'),'lastTrade':st.get('lastTradeSetTime'),'lastPx':(st.get('lastTradePx') or {}).get('value'),'traded':st.get('sharesTraded'),'settle':v['settle']}
    time.sleep(0.5)
json.dump(res,open('raw/closed_books_stats.json','w'),indent=0)
by=collections.defaultdict(list)
for s,r in res.items(): by[r['event']].append(r)
for ev,rs in sorted(by.items(),key=lambda x:x[1][0]['T']):
    t0=dt.datetime.fromisoformat(rs[0]['T']+':00+00:00')
    lt=[dt.datetime.fromisoformat(r['lastTrade'][:19]+'+00:00') for r in rs if r['lastTrade']]
    after=[x for x in lt if x>t0]
    mx=max(lt) if lt else None
    print(ev, rs[0]['T'], collections.Counter(r['state'] for r in rs), 'mkts',len(rs),'lastTrade>T:',len(after), 'max lastTrade-T (min):', round((mx-t0).total_seconds()/60,1) if mx else None)
