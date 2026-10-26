"""Up/Down: is PMUS mid a good estimate of P(close>=open | path)? Model vs market, and a taker sim at 1-5 min left."""
import json, math, sys, collections, bisect, datetime as dt, random
from statistics import NormalDist
N = NormalDist().cdf
THETA = 0.0695
fee = lambda p: THETA * p * (1 - p)
ALIGN = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # seconds to add to bar timestamp for the spot read
SER = sys.argv[2] if len(sys.argv) > 2 else 'btc-updown-15m'

ph = json.load(open('raw/ph_updown.json'))
B = json.load(open('raw/brti_5s.json'))
sym = SER.split('-')[0]
bk = sorted(int(k) for k in B[sym]); bv = [B[sym][str(k)][0] for k in bk]
# cumulative sums of squared 5s log returns for fast trailing RV
# cumulative squared 60-s returns (5-s BRTI returns are smoothed; use 60-s spacing)
r2 = [0.0] * len(bv)
for i in range(1, len(bv)):
    r2[i] = r2[i - 1] + (math.log(bv[i] / bv[i - 12]) ** 2 / 12 if i >= 12 else 0.0)

def spot(t):
    i = bisect.bisect_right(bk, t) - 1
    return bv[i] if i >= 0 else None

def rv(t, win):
    i = bisect.bisect_right(bk, t) - 1; j = bisect.bisect_right(bk, t - win) - 1
    if j < 1 or i - j < 20: return None
    return math.sqrt((r2[i] - r2[j]) / (5 * (i - j)))  # per sqrt-second

def ts(s): return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()

obs = []
for slug, d in ph.items():
    m = d['meta']
    if m['series'] != SER or not d['h']: continue
    ws, we = ts(m['ws']), ts(m['we']); O = float(m['ptb']); up = float(m['sp']) >= O
    for x in d['h']:
        tb = x['timestamp']
        if not (ws <= tb + 60 <= we - 60): continue
        ask = x['longPrice']; bid = 1 - x['shortPrice']
        if ask is None or bid is None or ask <= 0 or bid <= 0 or ask >= 1.0001: continue
        if not (0 < ask - bid <= 0.05): continue   # drop one-sided books (display price is not a quote)
        t = tb + ALIGN          # time of the spot read (bucket start; 5s bucket close ~ t+4.9s)
        S = spot(t)
        if S is None: continue
        tau = we - (tb + 60)    # bar at tb is the book at tb+60 (measured against the trade tape)
        if tau < 60: continue
        s60 = rv(t, 3600); s1d = rv(t, 86400); s15 = rv(t, 900)
        if not s60 or not s1d: continue
        obs.append(dict(slug=slug, tb=tb, tau=tau, ask=ask, bid=bid, mid=(ask + bid) / 2, up=up, x=math.log(S / O),
                        s60=s60, s1d=s1d, s15=s15 or s60, hour=dt.datetime.utcfromtimestamp(tb).hour,
                        wkd=dt.datetime.utcfromtimestamp(tb).weekday()))

def pm(o, s):
    return N(o['x'] / (s * math.sqrt(max(o['tau'] - 40, 1))))

for o in obs:
    o['p60'] = pm(o, o['s60']); o['p1d'] = pm(o, o['s1d']); o['p15'] = pm(o, o['s15'])
    o['pbl'] = pm(o, math.sqrt(0.5 * o['s60'] ** 2 + 0.5 * o['s1d'] ** 2))

def brier(xs, k): return sum((o[k] - o['up']) ** 2 for o in xs) / len(xs)
def ll(xs, k):
    e = 1e-4
    return -sum(math.log(min(max(o[k] if o['up'] else 1 - o[k], e), 1)) for o in xs) / len(xs)

print(f'series {SER} align +{ALIGN}s  windows {len({o["slug"] for o in obs})}  obs {len(obs)}')
buckets = [(60, 120), (120, 180), (180, 300), (300, 600), (600, 3600)]
print('min-left | n | Brier mid | p60 | p1d | p15 | blend | logloss mid | blend | spread med')
for a, b in buckets:
    xs = [o for o in obs if a <= o['tau'] < b and 0.03 < o['mid'] < 0.97]
    if len(xs) < 20: continue
    sp = sorted(o['ask'] - o['bid'] for o in xs)[len(xs) // 2]
    print(f'{a/60:.0f}-{b/60:.0f} | {len(xs)} | {brier(xs,"mid"):.4f} | {brier(xs,"p60"):.4f} | {brier(xs,"p1d"):.4f} | {brier(xs,"p15"):.4f} | {brier(xs,"pbl"):.4f} | {ll(xs,"mid"):.4f} | {ll(xs,"pbl"):.4f} | {sp:.3f}')

# implied vol vs realized
iv = []
for o in obs:
    if 0.1 < o['mid'] < 0.9 and abs(o['x']) > 1e-5:
        z = NormalDist().inv_cdf(o['mid'])
        if z * o['x'] > 0:
            iv.append((o['x'] / z / math.sqrt(o['tau'] - 40) * math.sqrt(31536000), o['s60'] * math.sqrt(31536000), o['s1d'] * math.sqrt(31536000)))
iv.sort()
if iv:
    q = lambda arr, p: sorted(arr)[int(p * (len(arr) - 1))]
    print('implied vol from mid: median %.3f (IQR %.3f-%.3f); trailing-60m RV median %.3f; trailing-24h RV median %.3f; n=%d' % (
        q([a for a, _, _ in iv], .5), q([a for a, _, _ in iv], .25), q([a for a, _, _ in iv], .75), q([b for _, b, _ in iv], .5), q([c for _, _, c in iv], .5), len(iv)))

# calibration of market mid by bucket
print('market mid calibration (tau 60-600s): bin | n | mean mid | win rate')
cal = collections.defaultdict(list)
for o in obs:
    if 60 <= o['tau'] < 600: cal[min(int(o['mid'] * 10), 9)].append(o)
for k in sorted(cal):
    xs = cal[k]; print(f'  {k/10:.1f} | {len(xs)} | {sum(o["mid"] for o in xs)/len(xs):.3f} | {sum(o["up"] for o in xs)/len(xs):.3f}')

# taker sim: one trade per window, first bar with tau in [lo,hi] where edge>thr
def sim(key, thr, lo, hi, one=True):
    pn = []; seen = set()
    for o in sorted(obs, key=lambda o: (o['slug'], o['tb'])):
        if not (lo <= o['tau'] <= hi): continue
        if one and o['slug'] in seen: continue
        p = o[key]
        ey = p - o['ask'] - fee(o['ask']); en = o['bid'] - p - fee(o['bid'])
        if ey > thr and o['ask'] < 0.99:
            pn.append(o['up'] - o['ask'] - fee(o['ask'])); seen.add(o['slug'])
        elif en > thr and o['bid'] > 0.01:
            pn.append((1 - o['up']) - (1 - o['bid']) - fee(o['bid'])); seen.add(o['slug'])
    if not pn: return '0'
    m = sum(pn) / len(pn); sd = math.sqrt(sum((x - m) ** 2 for x in pn) / max(1, len(pn) - 1))
    return f'n={len(pn)} mean={m:+.4f} se={sd/math.sqrt(len(pn)):.4f} hit={sum(x>0 for x in pn)/len(pn):.2f}'

print('taker sim (buy at bar ask / sell at bar bid, one trade per window):')
for key in ('pbl', 'p60', 'p1d'):
    for lo, hi in ((60, 300), (120, 300), (300, 600)):
        for thr in (0.0, 0.02, 0.05, 0.10):
            print(f'  {key} tau {lo}-{hi}s thr {thr:.2f}: {sim(key, thr, lo, hi)}')
# placebo: random side
random.seed(3)
json.dump([{k: o[k] for k in ('slug', 'tb', 'tau', 'ask', 'bid', 'up', 'x', 's60', 's1d', 'pbl', 'hour', 'wkd')} for o in obs], open(f'raw/ud_obs_{SER}_{ALIGN}.json', 'w'))
