"""Add a smile-consistent one-touch price (short-maturity local vol from the Deribit smile, Monte Carlo with
Brownian-bridge crossing correction) to the fair-value CSV.  usage: lv.py snap.json candles.json out.csv"""
import sys, math, csv
import numpy as np
snap_f, cand_f, out_f = sys.argv[1:4]
sys.argv = ['fv.py', snap_f, cand_f, out_f]
import fv  # runs the base model, writes out_f

rng = np.random.default_rng(11)
YEAR = fv.YEAR

def local_vol_fn(sf, T, S, t):
    ks = np.linspace(-1.2, 1.2, 241)
    F = S * sf.fwd_ratio(T)
    siv = np.array([sf.vol(F * math.exp(k), T, S, t)[0] for k in ks])
    d = np.gradient(siv, ks)
    den = siv - ks * d
    loc = np.where(den > 0.05, siv ** 2 / np.maximum(den, 1e-6), siv)
    atm = float(np.interp(0.0, ks, siv))
    loc = np.clip(loc, 0.5 * atm, 3 * atm)
    return ks, loc, F

def mc_touch(sf, B, T, S, t, kind, npath=20000, flat=None):
    tau = (T - t) / YEAR
    days = tau * 365
    dtm = 300 if days < 2 else (900 if days < 10 else 1800)
    n = max(20, int((T - t) / dtm))
    dt = tau / n
    ks, loc, F = local_vol_fn(sf, T, S, t)
    mu = math.log(F / S) / tau
    x = np.zeros(npath)  # log(S/S0)
    b = math.log(B / S)
    hit = np.zeros(npath, bool)
    for _ in range(n):
        sig = np.full(npath, flat) if flat else np.interp(x - math.log(F / S) * 0, ks, loc)
        x2 = x + (mu - 0.5 * sig ** 2) * dt + sig * math.sqrt(dt) * rng.standard_normal(npath)
        if kind == 'up':
            cross = x2 >= b
            pb = np.exp(-2 * np.maximum(b - x, 0) * np.maximum(b - x2, 0) / (sig ** 2 * dt))
        else:
            cross = x2 <= b
            pb = np.exp(-2 * np.maximum(x - b, 0) * np.maximum(x2 - b, 0) / (sig ** 2 * dt))
        hit |= cross | (rng.random(npath) < pb)
        x = x2
    return hit.mean()

rows = list(csv.DictReader(open(out_f)))
cache = {}
for r in rows:
    r['f_lv'] = ''
    if r['kind'] not in ('up', 'dn'):
        continue
    if r['bid'] == '' and r['ask'] == '':
        continue
    sf = fv.surf[r['sym']]
    m = next(m for m in fv.snap['markets'] if m['slug'] == r['slug'])
    T = fv.terms(m)[4]
    key = (r['sym'], r['kind'], r['K1'], round(T))
    if key not in cache:
        cache[key] = mc_touch(sf, float(r['K1']), T, float(r['S']), float(r['t']), r['kind'])
    r['f_lv'] = cache[key]
    f = cache[key]
    ask = float(r['ask']) if r['ask'] else None; bid = float(r['bid']) if r['bid'] else None
    r['evYes_lv'] = (f - ask - fv.fee(ask)) if ask else ''
    r['evNo_lv'] = (bid - f - fv.fee(bid)) if bid else ''
fields = list(rows[0].keys())
for k in ('f_lv', 'evYes_lv', 'evNo_lv'):
    if k not in fields: fields.append(k)
with open(out_f, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=fields, restval=''); w.writeheader(); w.writerows(rows)

# validation of the MC against the closed form at flat vol
sf = fv.surf['btc']; S = rows[0]['S']
t0 = fv.snap['t_start']; T = t0 + 5 * 86400
print('MC flat-vol check (B=+8%, 5d, 40%): MC', mc_touch(sf, 80200 * 1.08, T, 80200, t0, 'up', flat=0.40),
      'closed', fv.touch(80200, 80200 * 1.08, 0.40, 5 / 365, 0))
print('touch rows priced:', len(cache))
