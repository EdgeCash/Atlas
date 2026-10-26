import json, math, statistics as S, collections
rows = json.load(open('raw/metals_rows.json'))
def fee(p): return 0.0695*p*(1-p)
R = [r for r in rows if r['series'].endswith('15m') and 0 < r['ask_up'] < 1 and 0 < r['ask_dn'] < 1]
for r in R: r['mid'] = (r['ask_up'] + 1 - r['ask_dn'])/2
print('15m rows', len(R))
# bins of model-minus-mid
bins = [(-1,-0.15),(-0.15,-0.07),(-0.07,-0.03),(-0.03,0.03),(0.03,0.07),(0.07,0.15),(0.15,1)]
for metal in ['gold','silver']:
    print(metal)
    for lo, hi in bins:
        B = [r for r in R if r['metal']==metal and lo <= r['p']-r['mid'] < hi]
        if not B: continue
        print(f"  model-mid [{lo:+.2f},{hi:+.2f}) n {len(B):4d} windows {len(set(r['slug'] for r in B)):3d} mean mid {S.mean(r['mid'] for r in B):.3f} model {S.mean(r['p'] for r in B):.3f} realised {S.mean(r['y'] for r in B):.3f}")
# simple logistic regression via Newton: y ~ a + b*logit(model) + c*logit(mid)
def lg(p): p=min(max(p,0.005),0.995); return math.log(p/(1-p))
for metal in ['gold','silver']:
    X = [(1, lg(r['p']), lg(r['mid'])) for r in R if r['metal']==metal]; Y=[r['y'] for r in R if r['metal']==metal]
    w=[0,0,0]
    for it in range(30):
        g=[0,0,0]; H=[[0]*3 for _ in range(3)]
        for x,y in zip(X,Y):
            z=sum(a*b for a,b in zip(w,x)); p=1/(1+math.exp(-z))
            for i in range(3):
                g[i]+= (y-p)*x[i]
                for j in range(3): H[i][j]+= p*(1-p)*x[i]*x[j]
        # solve H d = g
        import copy
        A=[H[i]+[g[i]] for i in range(3)]
        for i in range(3):
            piv=A[i][i]
            for j in range(i,4): A[i][j]/=piv
            for k in range(3):
                if k!=i:
                    f=A[k][i]
                    for j in range(i,4): A[k][j]-=f*A[i][j]
        w=[w[i]+A[i][3] for i in range(3)]
    print(metal,'logit coefs (const, model, market mid):',[round(x,2) for x in w],'(rows correlated within window; treat as descriptive)')
# late-window certainty: last 3 minutes, model >= 0.97 on one side; what is that side's ask?
print('late window, tau<=180s, model side prob>=0.97')
c=collections.Counter(); L=[]
for r in R:
    if r['tau']<=180:
        for side,p,a,win in (('up',r['p'],r['ask_up'],r['y']==1),('dn',1-r['p'],r['ask_dn'],r['y']==0)):
            if p>=0.97: L.append((a,win,r['slug'],r['tau']))
print(' n',len(L),'asks dist',collections.Counter(round(a,2) for a,_,_,_ in L).most_common(8),'wins',sum(w for _,w,_,_ in L))
cheap=[x for x in L if x[0]<=0.97]
print(' with ask<=0.97:',len(cheap),'wins',sum(w for _,w,_,_ in cheap), 'pnl/contract', S.mean([(1 if w else 0)-a-fee(a) for a,w,_,_ in cheap]) if cheap else None)
