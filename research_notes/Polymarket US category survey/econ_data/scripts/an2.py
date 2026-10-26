import json,datetime as dt,collections
H=json.load(open('raw/closed_hist_1m.json'))
fee=lambda p:0.0695*p*(1-p)
byev=collections.defaultdict(list)
for s,v in H.items(): byev[v['event']].append((s,v))
summary=[]
for ev,lst in sorted(byev.items(),key=lambda x:x[1][0][1]['T']):
    t0=int(dt.datetime.fromisoformat(lst[0][1]['T']+':00+00:00').timestamp())
    evrows=[]
    for s,v in lst:
        h=[(int(x['timestamp']),x.get('longPrice'),x.get('shortPrice')) for x in v['h'] if x.get('longPrice') is not None]
        if not h: continue
        S=float(json.loads(v['settle'])[0])
        post=[(t,(p if S==1 else q)) for t,p,q in h if t>=t0+60]   # winning-side ask, from minute +1 on (assume minute 0 unusable)
        good=[(t,a) for t,a in post if a is not None and a<=0.97 and a>0]
        if good:
            best=min(a for t,a in good); net=1-best-fee(best)
            first=(good[0][0]-t0)//60; last=(good[-1][0]-t0)//60
            evrows.append((v['title'],S,len(good),first,last,best,round(net,3)))
    tot=sum(r[2] for r in evrows)
    print(f"## {ev} T={lst[0][1]['T']}: markets w/ winning-side ask<=0.97 after +1m: {len(evrows)}")
    for r in sorted(evrows,key=lambda r:-r[6]): print('   ',r)
