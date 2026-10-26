import json, sys, datetime as dt, glob, os
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
rows = []
for f in ("live1.jsonl", "live2.jsonl", "live3.jsonl", "live4.jsonl"):
    if os.path.exists(f): rows += [json.loads(l) for l in open(f)]
rows.sort(key=lambda r: r["t"])
T = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
ESPN_ABBR = {"uta": "UTAH", "ny": "NY", "gs": "GS", "sa": "SA", "no": "NO", "was": "WSH", "nj": "NJ", "mon": "MTL", "la": "LA"}
slugs = sorted({r["slug"] for r in rows if r["kind"] == "ev" and r.get("ended")})
out = []
for s in slugs:
    lg, a, h = s.split("-")[:3]
    ev = [r for r in rows if r.get("slug") == s and r["kind"] == "ev"]
    bk = [r for r in rows if r.get("slug") == s and r["kind"] == "book"]
    e1 = next(r for r in ev if r.get("ended")); prev = [r for r in ev if r["t"] < e1["t"]]
    fin_ts = e1.get("finTs")
    long_wins = float(e1.get("bb") or 0) >= 0.5 if e1.get("bb") else (float(e1.get("ba") or 1) > 0.5)
    rsv = next((r["t"] for r in ev if r.get("mstatus") == "MARKET_STATUS_RESOLVING"), None)
    rsd = next((r["t"] for r in ev if r.get("mstatus") == "MARKET_STATUS_RESOLVED"), None)
    A, H = ESPN_ABBR.get(a, a).upper(), ESPN_ABBR.get(h, h).upper()
    esp = None; esp_prev = None; esp_score = None
    for r in rows:
        if r["kind"] != "espn" or r.get("lg") != lg: continue
        for c in r["comps"]:
            parts = c["name"].upper().replace(" VS ", " @ ").split(" @ ")
            if len(parts) == 2 and parts[0] == A and parts[1] == H:
                if c["completed"] and not esp: esp = r["t"]; esp_score = c["score"]
                elif not c["completed"] and not esp: esp_prev = r["t"]
    nhl = None
    if lg == "nhl":
        for r in rows:
            if r["kind"] == "nhlapi":
                for g in r["games"]:
                    if str(g.get("h", "")).lower()[:3] == h[:3] and g["state"] in ("FINAL", "OFF") and not nhl: nhl = (r["t"], g["state"])
    # winner ask path in book: last time winner had an ask <= 0.99 (any), and asks after FT
    def wask(b):
        if long_wins: return b.get("ba"), b.get("long_ask_le0.99"), b.get("long_ask_le0.98")
        return (None if b.get("bb") is None else round(1 - b["bb"], 4)), b.get("short_ask_le0.99"), b.get("short_ask_le0.98")
    post = [b for b in bk if b["t"] >= e1["t"] and (not rsv or b["t"] < rsv) and b.get("state") == "MARKET_STATE_OPEN"]
    post_asks = [wask(b) for b in post]
    pre = [b for b in bk if b["t"] < e1["t"] and b.get("state") == "MARKET_STATE_OPEN"]
    last_le99 = None
    for b in pre:
        wa = wask(b)[0]
        if wa is not None and wa <= 0.99 + 1e-9: last_le99 = b["t"]
    out.append(dict(slug=s, gw_ft_poll=e1["t"][11:19], gw_prev_poll=prev[-1]["t"][11:19] if prev else None, gw_prev_period=prev[-1]["period"] if prev else None,
                    finTs=(fin_ts or "")[11:19], espn_final=(esp or "")[11:19], espn_prev=(esp_prev or "")[11:19], espn_score=esp_score, gw_score=e1["score"],
                    espn_minus_gw_s=round((T(esp) - T(fin_ts)).total_seconds(), 1) if esp and fin_ts else None,
                    nhl=nhl, resolving=(rsv or "")[11:19], resolved=(rsd or "")[11:19],
                    window_s=round((T(rsv) - T(fin_ts)).total_seconds()) if rsv and fin_ts else None,
                    settle_s=round((T(rsd) - T(fin_ts)).total_seconds()) if rsd and fin_ts else None,
                    last_winner_ask_le99_before_ft=(last_le99 or "")[11:19],
                    lead_s=round((T(fin_ts) - T(last_le99)).total_seconds()) if last_le99 and fin_ts else None,
                    post_polls=len(post), post_any_ask_le99=sum(1 for x in post_asks if x[0] is not None and x[0] <= 0.99 + 1e-9),
                    post_max_depth_le99=max([x[1] or 0 for x in post_asks] or [0]), post_best_asks=sorted({x[0] for x in post_asks if x[0] is not None})[:3]))
for o in out: print(json.dumps(o))
json.dump(out, open("sports_latency.json", "w"), indent=1)
