import json, datetime as dt, statistics as st, collections, sys
by = collections.defaultdict(list); anom = collections.Counter(); lastpx = collections.defaultdict(collections.Counter); n = collections.Counter()
for l in open(sys.argv[1]):
    r = json.loads(l); n[r["tag"]] += 1
    ts = (r.get("lps") or {}).get("ts")
    if not ts or not r.get("fin"): anom[(r["tag"], "no ts")] += 1; continue
    fin = dt.datetime.fromisoformat(r["fin"].replace("Z", "+00:00")); exp = dt.datetime.fromisoformat(ts[:26].rstrip("Z") + "+00:00")
    m = (exp - fin).total_seconds() / 60
    lp = float(r["lps"]["longPx"]["value"]); w = max(lp, 1 - lp)
    lastpx[r["tag"]][round(w, 4)] += 1
    if m < -1 or m > 180: anom[(r["tag"], "finishedTimestamp off")] += 1; continue
    by[r["tag"]].append(m)
for k, v in by.items():
    v.sort(); q = lambda p: v[min(len(v) - 1, int(p * len(v)))]
    print(f"{k}: n={len(v)} of {n[k]}  FT->book expiry minutes p10 {q(.1):.1f} p25 {q(.25):.1f} median {st.median(v):.1f} p75 {q(.75):.1f} p90 {q(.9):.1f} max {v[-1]:.1f}; >10 min: {sum(x>10 for x in v)}")
print(dict(anom)); print({k: dict(v) for k, v in lastpx.items()})
