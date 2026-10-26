import json, sys, math, collections, datetime as dt
rows = [json.loads(l) for l in open(sys.argv[1])]
TIGHT = float(sys.argv[2]) if len(sys.argv) > 2 else 1.04
def grp(r):
    s = r.get("series") or ""
    if r["tag"] in ("atp", "wta"): return "ATP/WTA" if "doubles" not in s else "ATP/WTA doubles"
    if r["tag"] == "itf": return "ITF"
    if "setka" in s: return "Setka Cup"
    if "czech" in s: return "Czech Liga Pro"
    return "Other TT (" + s.split("-20")[0] + ")"
pos = []
stats = collections.Counter()
for r in rows:
    sides = r["sides"]
    if len(sides) != 2: stats["bad sides"] += 1; continue
    try: px = {bool(l): float(p) for _, p, l in sides}
    except Exception: stats["no settle"] += 1; continue
    if px.get(True) not in (0.0, 1.0) or px.get(False) not in (0.0, 1.0) or px[True] + px[False] != 1: stats["non-binary settle"] += 1; continue
    st = int(dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")).timestamp())
    h = [x for x in r.get("hist") or [] if x[0] is not None and x[0] <= st and x[1] and x[2]]
    h = [x for x in h if 0.01 < x[1] < 0.99 and 0.01 < x[2] < 0.99 and x[1] + x[2] <= TIGHT and not (x[1] == 0.5 and x[2] == 0.5)]
    if not h: stats["no tight pregame quote"] += 1; continue
    t, la, sa = h[-1]
    if st - t > 900: stats["quote >15min before start"] += 1; continue
    stats["used"] += 1
    theta = 0.10 if r["tag"] == "table-tennis" else 0.0695
    fav_long = la >= sa
    fa, da = (la, sa) if fav_long else (sa, la)
    fwon = px[True] if fav_long else px[False]
    fee = lambda p: theta * p * (1 - p)
    pos.append({"g": grp(r), "fa": fa, "da": da, "fwon": fwon, "ffee": fee(fa), "dfee": fee(da), "spread": la + sa - 1,
                "month": r["day"][:7], "day": r["day"]})
print(dict(stats))
B = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.99)]
def cell(ps, side):
    if not ps: return ""
    if side == "fav": x = [p["fwon"] - p["fa"] - p["ffee"] for p in ps]
    else: x = [(1 - p["fwon"]) - p["da"] - p["dfee"] for p in ps]
    n = len(x); m = sum(x) / n; sd = math.sqrt(sum((v - m) ** 2 for v in x) / max(1, n - 1)); se = sd / math.sqrt(n)
    return f"{100*m:+.1f} ± {100*se:.1f} ({n})"
groups = sorted(set(p["g"] for p in pos))
print("\nBuy the FAVOURITE at the last tight pregame ask (edge pts = win - ask - fee, ± SE, n)")
print("| group | " + " | ".join(f"{a:.1f}-{b:.2f}" for a, b in B) + " | all |")
for g in groups:
    ps = [p for p in pos if p["g"] == g]
    print(f"| {g} | " + " | ".join(cell([p for p in ps if a <= p['fa'] < b], 'fav') for a, b in B) + f" | {cell(ps,'fav')} |")
print("\nBuy the UNDERDOG (bucketed by favourite's ask)")
for g in groups:
    ps = [p for p in pos if p["g"] == g]
    print(f"| {g} | " + " | ".join(cell([p for p in ps if a <= p['fa'] < b], 'dog') for a, b in B) + f" | {cell(ps,'dog')} |")
print("\nCalibration: fav win rate vs mean fav ask by bucket")
for g in groups:
    ps = [p for p in pos if p["g"] == g]
    out = []
    for a, b in B:
        q = [p for p in ps if a <= p["fa"] < b]
        if q: out.append(f"{a:.1f}: {sum(p['fwon'] for p in q)/len(q):.3f} vs {sum(p['fa'] for p in q)/len(q):.3f} (n={len(q)})")
    print(g, "; ".join(out))
print("\nBy month, underdog all buckets 0.6-0.9")
for g in groups:
    ps = [p for p in pos if p["g"] == g and 0.6 <= p["fa"] < 0.9]
    print(g, {m: cell([p for p in ps if p["month"] == m], "dog") for m in sorted(set(p["month"] for p in ps))})
print("\nmedian spread at kick-off", {g: sorted(p['spread'] for p in pos if p['g']==g)[len([p for p in pos if p['g']==g])//2] for g in groups})
