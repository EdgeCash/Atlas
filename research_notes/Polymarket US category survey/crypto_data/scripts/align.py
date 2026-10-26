import json,csv,datetime as dt,bisect,collections
ph=json.load(open('raw/ph_updown.json'))
want={s for s,d in ph.items() if d['meta']['series']=='btc-updown-15m' and d['h']}
def pt(s):
    base,frac=s[:19],s[19:]; sec=float('0.'+frac[1:].split('-')[0]) if frac.startswith('.') else 0
    return dt.datetime.fromisoformat(base+'-04:00').timestamp()+sec
tr=collections.defaultdict(list)
for f in ('raw/tas_crypto_20261020.csv','raw/tas_crypto_20261022.csv','raw/tas_crypto_20261024.csv'):
    for t,s,p,q in csv.reader(open(f)):
        if s in want: tr[s].append((pt(t),float(p)))
res=collections.defaultdict(lambda:[0.0,0])
for s,tt in tr.items():
    tt.sort(); T=[x[0] for x in tt]
    for b in ph[s]['h']:
        mid=(b['longPrice']+1-b['shortPrice'])/2
        if not 0.1<mid<0.9: continue
        for off in (-30,0,15,30,45,60,75,90):
            i=bisect.bisect_right(T,b['timestamp']+off)-1
            if i<0 or b['timestamp']+off-T[i]>10: continue
            res[off][0]+=abs(tt[i][1]-mid); res[off][1]+=1
for off in sorted(res): print('bar ts +%3ds: mean |last trade - bar mid| = %.4f n=%d'%(off,res[off][0]/res[off][1],res[off][1]))
