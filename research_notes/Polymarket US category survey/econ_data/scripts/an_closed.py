import json,datetime as dt,collections
H=json.load(open('raw/closed_hist_1m.json'))
byev=collections.defaultdict(list)
for s,v in H.items(): byev[v['event']].append((s,v))
for ev,lst in sorted(byev.items(),key=lambda x:x[1][0][1]['T']):
    t0=int(dt.datetime.fromisoformat(lst[0][1]['T']+':00+00:00').timestamp())
    print(f"\n## {ev} T={lst[0][1]['T']}Z resolved {lst[0][1]['resolved_at']}")
    for s,v in sorted(lst,key=lambda x:x[1]['title'] or ''):
        h=[(int(x['timestamp']),x.get('longPrice'),x.get('shortPrice')) for x in v['h']]
        if not h: print('  ',v['title'],'NO HIST',v['err']); continue
        S=json.loads(v['settle'])[0]; S=float(S)
        pre=[p for t,p,q in h if t<t0]; post=[(t,p,q) for t,p,q in h if t>=t0]
        p_m1=pre[-1] if pre else None
        # last minute where price changed
        lastchg=None
        for i in range(1,len(h)):
            if (h[i][1],h[i][2])!=(h[i-1][1],h[i-1][2]): lastchg=h[i][0]
        nchg_post=sum(1 for i in range(1,len(h)) if h[i][0]>=t0 and (h[i][1],h[i][2])!=(h[i-1][1],h[i-1][2]))
        wrong=[t for t,p,q in post if p is not None and ((S==0 and p>=0.05) or (S==1 and p<=0.95))]
        # contiguous wrong minutes from t0
        k=0
        for t,p,q in post:
            if p is not None and ((S==0 and p>=0.05) or (S==1 and p<=0.95)): k+=1
            else: break
        path=' '.join(f"{p}" for t,p,q in post[:8])
        lc=(lastchg-t0)//60 if lastchg else None
        print(f"  {str(v['title'])[:26]:26s} S={S:.0f} p-1={p_m1} post0-7=[{path}] chg_post={nchg_post} lastchg@{lc}m wrong_min={len(wrong)} contig={k}")
