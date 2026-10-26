import json,csv,math,datetime as dt,collections,sys
from statistics import NormalDist
inv=NormalDist().inv_cdf
br={int(k):v for k,v in json.load(open('raw/brti_1s_sample.json')).items()}
cm={m['slug']:m for m in json.load(open('raw/closed_markets.json')) if m['series']=='btc-updown-15m' and m['ptb']}
ts=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def pt(s):
    base,frac=s[:19],s[19:]; sec=float('0.'+frac[1:].split('-')[0]) if frac.startswith('.') else 0
    return dt.datetime.fromisoformat(base+'-04:00').timestamp()+sec
last=collections.defaultdict(dict)
for f in ('raw/tas_crypto_20261024.csv','raw/tas_crypto_20261022.csv'):
    for t,s,p,q in csv.reader(open(f)):
        if s in cm and 'btc-updown-15m' in s:
            tt=pt(t)
            if int(tt) in br: last[s][int(tt)]=float(p)
STEP=int(sys.argv[1]) if len(sys.argv)>1 else 2
num=collections.defaultdict(float); den1=collections.defaultdict(float); den2=collections.defaultdict(float); cnt=collections.Counter()
for s,lp in last.items():
    m=cm[s]; T1=ts(m['we']); T0=ts(m['ws']); O=float(m['ptb'])
    # forward-filled implied z at every second
    z={}; cur=None
    for k in range(int(T0)+30,int(T1)-120):
        if k in lp: cur=lp[k]
        if cur and 0.03<cur<0.97: z[k]=inv(cur)*math.sqrt(T1-k-40)
    ks=sorted(z)
    for k in ks[::STEP]:
        if k+STEP not in z: continue
        dz=z[k+STEP]-z[k]
        for L in range(-20,31):
            a=k-L; b=k+STEP-L
            if a in br and b in br:
                dy=math.log(br[b]/br[a])
                num[L]+=dz*dy; den1[L]+=dz*dz; den2[L]+=dy*dy; cnt[L]+=1
print('corr(d implied-z of trade price over [t,t+%ds], d log BRTI over [t-L,t+%d-L]) — positive L = trades lag BRTI'%(STEP,STEP))
for L in sorted(num):
    if L%2==0 or abs(L)<=3: print(f'L={L:+d}s corr={num[L]/math.sqrt(den1[L]*den2[L]):.3f} n={cnt[L]}')
