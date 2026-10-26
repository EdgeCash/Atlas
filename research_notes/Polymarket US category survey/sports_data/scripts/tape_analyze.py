import json, sys, datetime as dt, collections
c = collections.defaultdict(collections.Counter); ex = []
for l in open(sys.argv[1]):
    r = json.loads(l)
    try: px = {bool(lg): float(p) for _, p, lg in r["sides"]}
    except Exception: continue
    if sorted(px.values()) != [0.0, 1.0]: c[r["tag"]]["non-binary"] += 1; continue
    wl = px[True] == 1.0
    fin = int(dt.datetime.fromisoformat(r["fin"].replace("Z", "+00:00")).timestamp())
    exp = int(dt.datetime.fromisoformat(r["lps"]["ts"][:26].rstrip("Z") + "+00:00").timestamp())
    win = [(t, (lp if wl else sp), (sp if wl else lp)) for t, lp, sp in r["tape"] if t is not None and fin <= t <= exp and lp is not None]
    pre = [(t, (lp if wl else sp)) for t, lp, sp in r["tape"] if t is not None and fin - 300 <= t < fin and lp is not None]
    k = r["tag"]; c[k]["games"] += 1
    c[k]["window minutes (tape points)"] += len(win)
    if not win: c[k]["no tape point in window"] += 1
    for thr, name in ((0.98, "<=0.98"), (0.97, "<=0.97"), (0.95, "<=0.95")):
        g = [x for x in win if x[1] <= thr + 1e-9]
        if g: c[k][f"games winner ask {name} in window"] += 1
        if g and any(x[2] <= 0.02 for x in g): c[k][f"games winner {name} & loser<=0.02"] += 1
    if any(x[1] <= 0.98 for x in win): ex.append((k, r["slug"], [(dt.datetime.fromtimestamp(t, dt.UTC).strftime('%H:%M'), w, lo) for t, w, lo in win][:6], (exp - fin) / 60))
    if any(x[1] <= 0.98 for x in pre): c[k]["games winner <=0.98 in 5 min pre-FT"] += 1
for k, v in c.items(): print(k, dict(v))
for e in ex[:30]: print(e)
