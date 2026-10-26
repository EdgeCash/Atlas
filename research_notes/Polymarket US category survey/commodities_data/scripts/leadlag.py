import json, math, bisect, statistics as S
exec(open('scripts/metals_model.py').read().split('# 1) ptb check')[0])
d = json.load(open('raw/metals_hist.json'))
for metal in ['gold','silver']:
    for k in [-60,-30,0,15,30,45,60,90,120]:
        se=[]; br=[]
        for slug, v in d.items():
            if metal not in slug or not slug.split('-')[-2]=='15m' and '15m' not in slug: continue
            if '15m' not in v['series'] or not v['ptb'] or not v['settle']: continue
            s0=float(v['ptb']['value'])
            for x in (v['hist'] or {}).get('history',[]):
                t=x['timestamp']
                if not (v['ws']+60<=t<v['we']-60): continue
                if not (0<x['longPrice']<1 and 0<x['shortPrice']<1): continue
                mid=(x['longPrice']+1-x['shortPrice'])/2
                tt=min(t+k, v['we']); St=px_at(metal, tt); var=rv(metal, t)
                if not St or not var: continue
                tau=max(v['we']-tt,1)
                p=Phi(math.log(St/s0)/math.sqrt(var*tau))
                se.append((p-mid)**2)
        print(metal,'shift',k,'n',len(se),'mean sq diff model-vs-mid',round(S.mean(se),4))
