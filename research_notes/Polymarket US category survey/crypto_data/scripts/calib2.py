import csv,json,re,collections,math,sys
cm={}
for m in json.load(open('raw/closed_markets.json')):
    try:
        op=json.loads(m['outcomePrices'] or '[]')
        if op: cm[m['slug']]=float(op[0])
    except Exception: pass
B=[0.5,0.6,0.7,0.8,0.9,0.95,0.98,1.001]
for fam in ('updown-15m','updown-5m','updown-1h'):
  # per window per bin: shares, cost, wins
  w=collections.defaultdict(lambda:[0.0,0.0,0.0])
  for f in sys.argv[1:]:
    for t,s,p,q in csv.reader(open(f)):
        if fam not in s or s not in cm or not s.startswith('cpc-btc'): continue
        p=float(p);q=float(q);y=cm[s]
        if p<0.5: p,y=1-p,1-y
        b=next(i for i in range(len(B)-1) if B[i]<=p<B[i+1])
        a=w[(s,b)];a[0]+=q;a[1]+=q*p;a[2]+=q*y
  print('==',fam,'(BTC, folded to favourite side; SE clustered by window)  bin | windows | avg price | win rate | edge pts ± se')
  for b in range(len(B)-1):
    xs=[v for (s,bb),v in w.items() if bb==b]
    if len(xs)<20: continue
    # window-level: weight by shares
    S=sum(v[0] for v in xs); P=sum(v[1] for v in xs)/S; Y=sum(v[2] for v in xs)/S
    # cluster SE of (y-p) share-weighted
    d=[(v[2]-v[1])/v[0] for v in xs]; wt=[v[0]/S for v in xs]
    m=sum(a*b2 for a,b2 in zip(d,wt)); var=sum((b2**2)*(a-m)**2 for a,b2 in zip(d,wt))*len(xs)/(len(xs)-1)
    print(f'  {B[b]:.2f}-{B[b+1]:.2f} | {len(xs)} | {P:.3f} | {Y:.3f} | {100*(Y-P):+.1f} ± {100*math.sqrt(var):.1f}')
