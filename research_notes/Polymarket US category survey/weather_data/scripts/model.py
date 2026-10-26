import json, collections, math
resid = {tuple(k.split('|')): v for k, v in json.load(open('raw/resid.json')).items()}
def dist(kind, lead, station, exclude_date=None, pool_w=0.3, before=None):
    """P(CLI - txn = k): station empirical residuals mixed with pooled (bias-corrected) residuals, smoothed."""
    rows = resid[(kind, lead)]
    rows = [r for r in rows if r[1] != exclude_date and (before is None or r[1] < before)]
    st = [r[2] for r in rows if r[0] == station]
    pool = [r[2] for r in rows]
    if len(st) < 20:
        st_b = sum(st)/len(st) if st else 0
    pb = sum(pool)/len(pool)
    c = collections.Counter()
    for r in st: c[r] += (1 - pool_w) / len(st)
    sb = sum(st)/len(st) if st else 0
    for r in pool: c[round(r - pb + sb)] += pool_w / len(pool)
    # smooth with [0.15,0.7,0.15] kernel
    s = collections.Counter()
    for k, p in c.items():
        s[k-1] += 0.15*p; s[k] += 0.7*p; s[k+1] += 0.15*p
    return s
def bucket_probs(txn, d, buckets):
    out = []
    for lo, hi in buckets:
        out.append(sum(p for k, p in d.items() if lo <= txn + k <= hi))
    return out
def fee(p): return 0.0695 * p * (1 - p)
