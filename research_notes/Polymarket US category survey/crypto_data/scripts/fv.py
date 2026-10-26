"""Fair value of PMUS crypto ladders from Deribit implied vol, realized vol and an empirical (bootstrap) model.
usage: python3 fv.py snap.json candles.json out.csv
"""
import json, sys, math, re, csv, bisect, datetime as dt
from statistics import NormalDist
N = NormalDist().cdf
phi = NormalDist().pdf
THETA = 0.0695
YEAR = 365.0 * 86400

snap = json.load(open(sys.argv[1]))
cd = json.load(open(sys.argv[2]))
OUT = sys.argv[3]

MON = dict(JAN=1, FEB=2, MAR=3, APR=4, MAY=5, JUN=6, JUL=7, AUG=8, SEP=9, OCT=10, NOV=11, DEC=12)


def parse_exp(s):
    m = re.match(r'(\d+)([A-Z]{3})(\d\d)', s)
    return dt.datetime(2000 + int(m.group(3)), MON[m.group(2)], int(m.group(1)), 8, tzinfo=dt.timezone.utc).timestamp()


# ---------- spot (BRTI 1s) ----------
brti = {}
for ser in snap['brti_window']['series']:
    sym = ser['asset']['symbol']
    brti[sym] = sorted((c['timestamp'], float(c['close'])) for c in ser['candles'])


def spot(sym, t):
    a = brti[sym]
    i = bisect.bisect_left([x[0] for x in a], t)
    i = min(max(i, 0), len(a) - 1)
    return a[i][1]


# ---------- Deribit surface ----------
class Surface:
    def __init__(self, res):
        idx = res[0]['estimated_delivery_price']
        self.S0 = idx
        ex = {}
        for x in res:
            _, e, k, cp = x['instrument_name'].split('-')
            if not x.get('mark_iv'):
                continue
            K = float(k)
            T = parse_exp(e)
            F = x['underlying_price']
            d = ex.setdefault(T, {'F': F, 'pts': {}})
            # OTM side only
            if (cp == 'C' and K >= F) or (cp == 'P' and K < F):
                d['pts'][math.log(K / F)] = x['mark_iv'] / 100.0
        self.exp = []
        for T in sorted(ex):
            pts = sorted(ex[T]['pts'].items())
            if len(pts) < 5:
                continue
            self.exp.append((T, ex[T]['F'] / idx, [p[0] for p in pts], [p[1] for p in pts]))

    @staticmethod
    def _iv(ks, vs, k):
        if k <= ks[0]:
            return vs[0]
        if k >= ks[-1]:
            return vs[-1]
        i = bisect.bisect_left(ks, k)
        w = (k - ks[i - 1]) / (ks[i] - ks[i - 1])
        return vs[i - 1] + w * (vs[i] - vs[i - 1])

    def fwd_ratio(self, T):
        e = self.exp
        if T <= e[0][0]:
            return 1 + (e[0][1] - 1) * max(0, (T - self.t0)) / (e[0][0] - self.t0)
        for a, b in zip(e, e[1:]):
            if a[0] <= T <= b[0]:
                w = (T - a[0]) / (b[0] - a[0])
                return a[1] + w * (b[1] - a[1])
        return e[-1][1]

    def vol(self, K, T, S, t):
        """implied vol at strike K for maturity T, spot S at time t (sticky moneyness)."""
        F = S * self.fwd_ratio(T)
        k = math.log(K / F)
        tau = (T - t) / YEAR
        e = self.exp
        def w_of(i):
            Ti, fr, ks, vs = e[i]
            ti = (Ti - t) / YEAR
            return self._iv(ks, vs, k) ** 2 * ti, ti
        if T <= e[0][0]:
            w1, t1 = w_of(0)
            return math.sqrt(w1 / t1), F
        for i in range(len(e) - 1):
            if e[i][0] <= T <= e[i + 1][0]:
                w1, t1 = w_of(i); w2, t2 = w_of(i + 1)
                w = w1 + (w2 - w1) * (tau - t1) / (t2 - t1)
                return math.sqrt(max(w, 1e-12) / tau), F
        w1, t1 = w_of(len(e) - 1)
        return math.sqrt(w1 / t1), F


def black_call(F, K, s, tau):
    if tau <= 0:
        return max(F - K, 0)
    sd = s * math.sqrt(tau)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    return F * N(d1) - K * N(d1 - sd)


def digital_smile(surf, K, T, S, t):
    tau = (T - t) / YEAR
    h = K * 0.003
    s1, F = surf.vol(K - h, T, S, t)
    s2, _ = surf.vol(K + h, T, S, t)
    return (black_call(F, K - h, s1, tau) - black_call(F, K + h, s2, tau)) / (2 * h)


def digital_flat(F, K, s, tau):
    sd = s * math.sqrt(tau)
    return N((math.log(F / K) - 0.5 * sd * sd) / sd)


def touch(S, B, s, tau, mu=0.0):
    """P(path touches B before tau) for GBM, log-drift mu (per year), vol s."""
    if tau <= 0:
        return float(S >= B) if B > S else float(S <= B)
    sd = s * math.sqrt(tau)
    if B > S:
        b = math.log(B / S); m = mu
    else:
        b = math.log(S / B); m = -mu
    return N((-b + m * tau) / sd) + math.exp(2 * m * b / (s * s)) * N((-b - m * tau) / sd)


# ---------- realized vol ----------
def rv(cs, per_year, n=None):
    closes = [c[4] for c in cs]
    if n:
        closes = closes[-(n + 1):]
    r = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1) * per_year), len(r)


RV = {}
for sym, p in (('btc', 'BTC-USD'), ('eth', 'ETH-USD')):
    RV[sym] = {
        '1m_24h': rv(cd[p + '_1m'], 525600, 1440)[0],
        '1h_7d': rv(cd[p + '_1h'], 8760, 168)[0],
        '1h_30d': rv(cd[p + '_1h'], 8760, 720)[0],
        '1d_90d': rv(cd[p + '_1d'], 365, 90)[0],
    }

# ---------- empirical (vol-normalised) touch / terminal from daily OHLC ----------
EMP = {}
for sym, p in (('btc', 'BTC-USD'), ('eth', 'ETH-USD')):
    d = cd[p + '_1d']
    cl = [c[4] for c in d]; hi = [c[2] for c in d]; lo = [c[1] for c in d]
    lr = [0.0] + [math.log(b / a) for a, b in zip(cl, cl[1:])]
    sig = [None] * len(d)
    for i in range(31, len(d)):
        w = lr[i - 29:i + 1]; m = sum(w) / 30
        sig[i] = math.sqrt(sum((x - m) ** 2 for x in w) / 29 * 365)
    EMP[sym] = (cl, hi, lo, sig)
    RV[sym]['1d_30d'] = sig[-1]


def emp_probs(sym, kind, x, days, s_now):
    """kind: 'up'/'dn' touch, 'term' terminal >= ; x = log(B/S). vol-normalised daily-candle bootstrap since 2017."""
    cl, hi, lo, sig = EMP[sym]
    n = max(1, int(math.ceil(days)))
    zt = x / (s_now * math.sqrt(days / 365))
    hits = tot = 0
    start = 400 if sym == 'eth' else 200
    for i in range(start, len(cl) - n):
        if sig[i] is None:
            continue
        sc = sig[i] * math.sqrt(days / 365)
        if kind == 'up':
            z = math.log(max(hi[i + 1:i + 1 + n]) / cl[i]) / sc; ok = z >= zt
        elif kind == 'dn':
            z = math.log(min(lo[i + 1:i + 1 + n]) / cl[i]) / sc; ok = z <= zt
        else:
            z = math.log(cl[i + n] / cl[i]) / sc; ok = z >= zt
        hits += ok; tot += 1
    return hits / tot if tot else float('nan')


# ---------- market terms ----------
def et_midnight_after(y, m, d):
    # midnight ET at the end of y-m-d; EDT until Nov 1 2026 (06:00Z switch on Nov 1)
    t = dt.datetime(y, m, d, tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    off = 4 if t < dt.datetime(2026, 11, 1, 6, tzinfo=dt.timezone.utc) else 5
    return (t + dt.timedelta(hours=off)).timestamp()


def terms(m):
    apt = m['apt'] or {}
    slug = m['slug']
    sym = 'eth' if 'eth-' in slug else 'btc'
    if apt.get('marketType'):
        mt = apt['marketType'].replace('ASSET_PRICE_MARKET_TYPE_', '')
        T = dt.datetime.fromisoformat(apt['windowEnd'].replace('Z', '+00:00')).timestamp()
        if mt == 'ABOVE_BELOW':
            return sym, 'above', float(apt['strike']['value']), None, T
        if mt == 'ONE_TOUCH':
            kind = 'up' if apt['direction'].endswith('UP') else 'dn'
            return sym, kind, float(apt['strike']['value']), None, T
        if mt == 'RANGE':
            lo = apt.get('rangeLower'); hi = apt.get('rangeUpper')
            return sym, 'range', float(lo['value']) if lo else None, float(hi['value']) if hi else None, T
        return None
    # hand-listed
    mm = re.search(r'btc-(100k|150k)-(\d\d)-(\d\d)-(\d{4})$', slug)
    if mm:
        T = et_midnight_after(int(mm.group(4)), int(mm.group(2)), int(mm.group(3)))
        return 'btc', 'up', (100000.0 if mm.group(1) == '100k' else 149999.99), None, T
    T = et_midnight_after(2026, 12, 31)
    mm = re.search(r'above-yr-12-31-2026-(\d+)k$', slug)
    if mm:
        return 'btc', 'up', float(mm.group(1)) * 1000, None, T
    mm = re.search(r'hitprice-high-yr-12-31-2026-(\d+)k$', slug)
    if mm:
        return 'btc', 'up', float(mm.group(1)) * 1000 - 0.01, None, T
    mm = re.search(r'hitprice-low-yr-12-31-2026-(\d+)k$', slug)
    if mm:
        return 'btc', 'dn', float(mm.group(1)) * 1000, None, T
    mm = re.search(r'pricerange-yr-12-31-2026-(\d+)$', slug)
    if mm:
        c = float(mm.group(1)); return 'btc', 'range', c - 2500, c + 2499.99, T
    if slug.endswith('above-150k'):
        return 'btc', 'range', 150000.0, None, T
    if slug.endswith('below-20k'):
        return 'btc', 'range', None, 19999.99, T
    return None


surf = {'btc': Surface(snap['deribit_BTC']['result']), 'eth': Surface(snap['deribit_ETH']['result'])}
for s in surf.values():
    s.t0 = snap['t_start']


def fee(p):
    return THETA * p * (1 - p)


rows = []
for m in snap['markets']:
    tr = terms(m)
    if not tr:
        continue
    sym, kind, K1, K2, T = tr
    t = m['t']
    if T <= t + 60:
        continue
    S = spot(sym, t)
    tau = (T - t) / YEAR
    days = tau * 365
    sf = surf[sym]
    r = RV[sym]
    s_rv = r['1h_7d']
    s_emp = r['1d_30d']
    mu = math.log(sf.fwd_ratio(T)) / tau if tau > 0 else 0
    if kind == 'above':
        f_iv = digital_smile(sf, K1, T, S, t)
        siv, F = sf.vol(K1, T, S, t)
        f_rv = digital_flat(S, K1, s_rv, tau)
        f_emp = emp_probs(sym, 'term', math.log(K1 / S), days, s_emp) if days >= 1 else float('nan')
        f_alt = digital_flat(S, K1, r['1h_30d'], tau)
    elif kind in ('up', 'dn'):
        siv, F = sf.vol(K1, T, S, t)
        f_iv = touch(S, K1, siv, tau, mu - 0.5 * siv * siv)
        f_rv = touch(S, K1, s_rv, tau, 0.0)
        f_emp = emp_probs(sym, kind, math.log(K1 / S), days, s_emp) if days >= 1 else float('nan')
        # alt: 2x smile digital (reflection principle)
        d = digital_smile(sf, K1, T, S, t)
        f_alt = min(1.0, 2 * (d if kind == 'up' else 1 - d))
    else:  # range [K1, K2]
        up = digital_smile(sf, K1, T, S, t) if K1 else 1.0
        dn = digital_smile(sf, K2 + 0.01, T, S, t) if K2 else 0.0
        f_iv = up - dn
        siv, F = sf.vol(K1 or K2, T, S, t)
        f_rv = (digital_flat(S, K1, s_rv, tau) if K1 else 1) - (digital_flat(S, K2 + .01, s_rv, tau) if K2 else 0)
        f_emp = float('nan'); f_alt = float('nan')
    bb = m['bids'][0] if m['bids'] else (None, 0)
    ba = m['offers'][0] if m['offers'] else (None, 0)
    row = dict(slug=m['slug'], event=m['event'], sym=sym, kind=kind, K1=K1, K2=K2, days=round(days, 3), S=S, iv=round(siv, 4),
               rv7=round(s_rv, 4), f_iv=f_iv, f_rv=f_rv, f_emp=f_emp, f_alt=f_alt,
               bid=bb[0], bid_qty=bb[1], ask=ba[0], ask_qty=ba[1], traded=float(m.get('traded') or 0), oi=float(m.get('oi') or 0),
               notional=float(m.get('notional') or 0), t=t)
    for lab, f in (('iv', f_iv), ('rv', f_rv), ('emp', f_emp)):
        row['evYes_' + lab] = (f - ba[0] - fee(ba[0])) if ba[0] else None
        row['evNo_' + lab] = (bb[0] - f - fee(bb[0])) if bb[0] else None
    rows.append(row)

with open(OUT, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print('RV', json.dumps({k: {a: round(b, 3) for a, b in v.items()} for k, v in RV.items()}))
for sym in surf:
    print(sym, 'S0', surf[sym].S0, [(dt.datetime.utcfromtimestamp(e[0]).strftime('%d%b'), round(e[1], 4), round(Surface._iv(e[2], e[3], 0.0), 3)) for e in surf[sym].exp])
print(len(rows), 'rows ->', OUT)
