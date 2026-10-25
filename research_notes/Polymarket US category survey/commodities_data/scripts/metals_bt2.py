import json, math, bisect, statistics as S, collections
exec(open('scripts/metals_model.py').read().split('# 1) ptb check')[0])
d = json.load(open('raw/metals_hist.json'))
SH=60
rows=[]
for slug, v in d.items():
    if not v['ptb'] or not v['settle']: continue
    metal='gold' if 'gold' in slug else 'silver'; s0=float(v['ptb']['value']); y=v['settle']['settlement']
    H=sorted((v['hist'] or {}).get('history',[]),key=lambda x:x['timestamp'])
    for x in H:
        t=x['timestamp']+SH
        if not (v['ws']+60<=t<v['we']): continue
        St=px_at(metal,t); var=rv(metal,t)
        if not St or not var: continue
        tau=v['we']-t
        for volname, vv in (('rv', var), ('gvz', (0.2434 if metal=='gold' else 0.40)**2/(252*23*3600))):
            pass
        p=Phi(math.log(St/s0)/math.sqrt(var*tau))
        rows.append(dict(slug=slug,series=v['series'],metal=metal,t=t,tau=tau,p=p,au=x['longPrice'],ad=x['shortPrice'],y=y))
json.dump(rows,open('raw/metals_rows2.json','w'))
def brier(a,b): return S.mean((p-y)**2 for p,y in zip(a,b))
print('Brier, two-sided-quoted rows:')
for ser in sorted(set(r['series'] for r in rows)):
    R=[r for r in rows if r['series']==ser and 0<r['au']<1 and 0<r['ad']<1]
    if len(R)<50: continue
    mid=[(r['au']+1-r['ad'])/2 for r in R]; Y=[r['y'] for r in R]
    print(f"  {ser:18s} n {len(R)} model {brier([r['p'] for r in R],Y):.4f} mid {brier(mid,Y):.4f} | median spread {S.median(r['au']+r['ad']-1 for r in R):.2f} | RMS(model-mid) {math.sqrt(S.mean((r['p']-m)**2 for r,m in zip(R,mid))):.3f}")
# strategy: every minute, take side with edge>thr; execution at NEXT stamped quote (one more minute of staleness, mimics 30s cache+45s poll)
print('Taker backtest (execution at next minute quote; one position per window per side max):')
byw=collections.defaultdict(list)
for r in rows: byw[r['slug']].append(r)
for ser in ['gold-updown-15m','silver-updown-15m','gold-updown-1h','silver-updown-1h']:
    for thr in [0.02,0.05,0.10]:
        for lag in [0,1]:
            P=[]
            for slug,R in byw.items():
                if not slug.endswith(tuple()) and R[0]['series']!=ser: continue
                if R[0]['series']!=ser: continue
                R.sort(key=lambda r:r['t']); taken=set()
                for i,r in enumerate(R):
                    if i+lag>=len(R): break
                    q=R[i+lag]
                    for side in ('u','d'):
                        if side in taken: continue
                        p=r['p'] if side=='u' else 1-r['p']; a=r['au'] if side=='u' else r['ad']; ae=q['au'] if side=='u' else q['ad']
                        if not (0.03<=a<=0.97 and 0<ae<1): continue
                        if p-a-fee(a)>thr:
                            win=(r['y']==1)==(side=='u'); P.append((1 if win else 0)-ae-fee(ae)); taken.add(side)
            if P: print(f"  {ser:18s} thr {thr:.2f} lag {lag}: trades {len(P):3d} mean {S.mean(P):+.3f} se {S.pstdev(P)/math.sqrt(len(P)):.3f} total/contract {sum(P):+.1f}")
