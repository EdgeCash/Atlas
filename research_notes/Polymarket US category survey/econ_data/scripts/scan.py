import json,re,sys
ev=json.load(open('raw/macro_econ_events.json')); B=json.load(open(sys.argv[1]))
fee=lambda p:0.0695*p*(1-p)
def lv(slug):
    md=B.get(slug,{}).get('marketData',{})
    bids=sorted([(float(x['px']['value']),float(x['qty'])) for x in md.get('bids',[])],reverse=True)
    offs=sorted([(float(x['px']['value']),float(x['qty'])) for x in md.get('offers',[])])
    return bids,offs
def num(t):
    t=t.replace(',','')
    m=re.search(r'(-?\d+(?:\.\d+)?)\s*([KMBT%]?)',t)
    v=float(m.group(1)); u=m.group(2)
    return v*{'K':1e3,'M':1e6,'B':1e9,'T':1e12}.get(u,1)
fam={}
for e in ev:
    s=e['slug']
    if s.startswith(('usgas','usbeef')): continue
    if any(x in s for x in ('lw-yr',)): kind='lte'
    elif s.startswith(('usfed-fomc','ecb-','boc-','boe-','boj-','bcb-')): kind='bucket'
    elif s.startswith(('cut-by','hike-by','usfed-2026','fed-gt','usfed-hike2','ussnap','usrx','usreal','usunion','usrent')): kind='other'
    else: kind='desc'
    fam[s]=(kind,[(m['slug'],m.get('title')) for m in e['markets']])
found=[]
for s,(kind,ms) in fam.items():
    if kind in ('desc','lte'):
        L=[]
        for slug,t in ms:
            try: L.append((num(t),slug,t))
            except: pass
        L.sort()
        # prob should be decreasing in x for desc, increasing for lte
        for i in range(len(L)):
            for j in range(len(L)):
                if i==j: continue
                xi,si,ti=L[i]; xj,sj,tj=L[j]
                # hi = should-have-higher-prob, lo = should-have-lower-prob
                if kind=='desc' and not xi<xj: continue
                if kind=='lte' and not xi>xj: continue
                bh,oh=lv(si); bl,ol=lv(sj)
                if not oh or not bl: continue
                # walk levels
                a=[list(x) for x in oh]; b=[list(x) for x in bl]
                ia=ib=0; qty=0; prof=0
                while ia<len(a) and ib<len(b):
                    pa=a[ia][0]; pb=b[ib][0]
                    edge=1-(pa+(1-pb))-fee(pa)-fee(1-pb)
                    if edge<=0: break
                    q=min(a[ia][1],b[ib][1]); qty+=q; prof+=q*edge
                    a[ia][1]-=q; b[ib][1]-=q
                    if a[ia][1]<=1e-9: ia+=1
                    if b[ib][1]<=1e-9: ib+=1
                if qty>0:
                    found.append((s,ti,oh[0],tj,bl[0],round(qty,2),round(prof,2), round(1-(oh[0][0]+1-bl[0][0]),3)))
    if kind=='bucket':
        asks=[];bids=[]
        for slug,t in ms:
            bb,oo=lv(slug); asks.append((t,oo[0] if oo else None)); bids.append((t,bb[0] if bb else None))
        sa=sum(x[1][0] for x in asks if x[1]) if all(x[1] for x in asks) else None
        sb=sum(x[1][0] for x in bids if x[1])
        nb=sum(1 for x in bids if x[1])
        print('BUCKET',s,'sum asks',sa,'sum bids',round(sb,3),'n bids',nb, [ (t,o) for t,o in asks])
for f in found: print('VIOL',f)
