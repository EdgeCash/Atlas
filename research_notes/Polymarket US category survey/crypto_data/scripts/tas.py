import csv,sys,re,collections,statistics as st
def fam(s):
    s2=re.sub(r'^cpc[a-z]*-','',s)
    m=re.match(r'([a-z0-9]+)-(updown-(?:5m|15m|1h|1d)|above-(?:hr|day|wk|yr)|range-(?:hr|day|wk)|hit-[hl]-[wm]|hitprice-(?:high|low)-yr|pricerange-yr|100k|150k)',s2)
    return (m.group(1)+'-'+m.group(2)) if m else 'other:'+s2[:20]
for f in sys.argv[1:]:
    agg=collections.defaultdict(lambda:[0,0.0,0.0,[] ,collections.Counter()])
    for row in csv.reader(open(f)):
        t,s,p,q=row; p=float(p);q=float(q)
        a=agg[fam(s)];a[0]+=1;a[1]+=q;a[2]+=p*q;a[3].append(p*q)
        a[4][int(p*100+1e-9)//10]+=p*q
    print('==',f)
    print('family | trades | shares | notional$ | median$ | p90$ | notional by price decile')
    for k,v in sorted(agg.items(),key=lambda kv:-kv[1][2]):
        if v[2]<200: continue
        x=sorted(v[3]);dec=' '.join(f"{d}:{v[4][d]/v[2]:.0%}" for d in sorted(v[4]) if v[4][d]/v[2]>=0.03)
        print(f"{k} | {v[0]} | {v[1]:.0f} | {v[2]:.0f} | {x[len(x)//2]:.2f} | {x[int(.9*len(x))]:.1f} | {dec}")
