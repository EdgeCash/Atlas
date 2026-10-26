"""Read-only poller: PMUS event state + /book (cache-busted) vs ESPN / league feeds, around game finishes."""
import json, time, sys, os, urllib.request, urllib.error, gzip, random, datetime as dt
OUT = sys.argv[1]
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 7000
MIN_GAP = 0.55
G = "https://gateway.polymarket.us"
LEAGUES = {"nfl": "football/nfl", "nba": "basketball/nba", "nhl": "hockey/nhl", "mlb": "baseball/mlb",
           "cfb": "football/college-football", "cbb": "basketball/mens-college-basketball", "wnba": "basketball/wnba"}
last_req = [0.0]
def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
def get(url, bust=True):
    gap = time.time() - last_req[0]
    if gap < MIN_GAP: time.sleep(MIN_GAP - gap)
    if bust: url += ("&" if "?" in url else "?") + "_=" + str(time.time_ns())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research-readonly", "Accept-Encoding": "gzip"})
    t0 = time.time(); last_req[0] = t0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip": body = gzip.decompress(body)
                h = {k.lower(): v for k, v in r.headers.items() if k.lower() in ("age", "cf-cache-status", "date", "cache-control", "last-modified")}
                return json.loads(body), h, round(time.time() - t0, 3)
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(2 + 3 * attempt); continue
            return None, {"err": e.code}, round(time.time() - t0, 3)
        except Exception as e:
            return None, {"err": type(e).__name__}, round(time.time() - t0, 3)
    return None, {"err": 429}, 0
f = open(OUT, "a")
def log(kind, **kw):
    kw.update(kind=kind, t=now()); f.write(json.dumps(kw) + "\n"); f.flush()
def league_of(e):
    s = (e.get("seriesSlug") or e.get("slug") or "").lower()
    for k in ("nfl", "nba", "nhl", "mlb", "wnba", "cfb", "cbb", "ncaaf", "ncaab", "ahl"):
        if s.startswith(k): return {"ncaaf": "cfb", "ncaab": "cbb"}.get(k, k)
    return None
LATE = ("Q4", "OT", "P3", "End Q4", "End P3", "2OT", "3OT", "SO", "OT1", "OT2", "4OT")
def is_late(e):
    p = str(e.get("period") or "")
    if e.get("ended"): return True
    if p in LATE or p.startswith("OT") or "OT" in p: return True
    if p.upper() in ("FT", "F", "FINAL", "VFT", "F/OT", "AOT"): return True
    lg = league_of(e)
    if lg == "mlb" and any(x in p for x in ("8", "9", "10", "11", "12", "13")): return True
    if lg == "cfb" and p in ("Q4",): return True
    if lg in ("nba", "cbb", "nfl", "cfb") and p in ("Q3", "End Q3", "H2", "2H"): return "warm"
    if lg in ("nhl", "ahl") and p in ("P2", "End P2"): return "warm"
    return False
def book_summary(b):
    md = (b or {}).get("marketData") or {}
    bids = [(float(x["px"]["value"]), float(x["qty"])) for x in md.get("bids") or []]
    offers = [(float(x["px"]["value"]), float(x["qty"])) for x in md.get("offers") or md.get("asks") or []]
    bids.sort(reverse=True); offers.sort()
    s = {"bb": bids[0][0] if bids else None, "ba": offers[0][0] if offers else None,
         "bbq": bids[0][1] if bids else None, "baq": offers[0][1] if offers else None,
         "nb": len(bids), "no": len(offers)}
    for c in (0.97, 0.98, 0.99, 0.995):
        s[f"long_ask_le{c}"] = round(sum(q for p, q in offers if p <= c + 1e-9), 2)
        s[f"short_ask_le{c}"] = round(sum(q for p, q in bids if p >= 1 - c - 1e-9), 2)  # short ask = 1 - long bid
    s["offers_hi"] = [o for o in offers if o[0] >= 0.95][:12]; s["offers_lo"] = [o for o in offers if o[0] <= 0.05][:12]
    s["bids_hi"] = [o for o in bids if o[0] >= 0.95][:12]; s["bids_lo"] = [o for o in bids if o[0] <= 0.05][:12]
    s["state"] = md.get("state") or md.get("marketState"); s["keys"] = list(md.keys())[:12]
    st = md.get("stats") or {}
    s["traded"] = st.get("sharesTraded"); s["oi"] = st.get("openInterest"); s["ltp"] = (st.get("lastTradePx") or {}).get("value"); s["tt"] = md.get("transactTime")
    return s
tracked = {}  # event slug -> dict
SEED = sys.argv[3] if len(sys.argv) > 3 else None
if SEED:
    for line in open(SEED):
        sl, lg, ml = line.split()
        tracked[sl] = {"lg": lg, "ml": ml, "final_seen": None, "done": False, "closed_seen": None, "late": True}
t_end = time.time() + DURATION; next_list = 0; next_feeds = {}; last_slow = {}
first_book_keys = True
while time.time() < t_end:
    if time.time() >= next_list:
        d, h, lat = get(G + "/v1/events?closed=false&live=true&limit=500".replace("/v1/v1", "/v1"))
        if d:
            for e in d.get("events", []):
                lg = league_of(e)
                if not lg: continue
                ml = [m for m in e.get("markets", []) if m.get("marketType") == "moneyline"]
                if not ml: continue
                if e["slug"] not in tracked:
                    tracked[e["slug"]] = {"lg": lg, "ml": ml[0]["slug"], "final_seen": None, "done": False, "closed_seen": None}
                    log("track", slug=e["slug"], lg=lg, ml=ml[0]["slug"], period=e.get("period"), score=e.get("score"))
        next_list = time.time() + 60
    hot_leagues = set()
    for slug, st in list(tracked.items()):
        if st["done"]: continue
        late = st.get("late")
        if not late and time.time() - last_slow.get(slug, 0) < 45: continue
        if late == "warm" and time.time() - last_slow.get(slug, 0) < 20: continue
        last_slow[slug] = time.time()
        d, h, lat = get(G + "/v1/events?slug=" + slug)
        e = (d or {}).get("events", [None])[0] if d else None
        if e:
            es = e.get("eventState") or {}
            m = next((m for m in e.get("markets", []) if m.get("slug") == st["ml"]), {})
            sides = [(s.get("description"), s.get("long")) for s in m.get("marketSides", [])]
            log("ev", slug=slug, lg=st["lg"], live=e.get("live"), ended=e.get("ended"), period=e.get("period"),
                elapsed=e.get("elapsed"), score=e.get("score"), es_upd=es.get("updatedAt"), es_period=es.get("period"),
                es_ended=es.get("ended"), finTs=e.get("finishedTimestamp") or es.get("finishedTimestamp"),
                mstatus=m.get("status"), mclosed=m.get("closed"), bb=(m.get("bestBidQuote") or {}).get("value"),
                ba=(m.get("bestAskQuote") or {}).get("value"), oprices=m.get("outcomePrices"), outcomes=m.get("outcomes"),
                sides=sides, tick=m.get("orderPriceMinTickSize"), fee=m.get("feeCoefficient"), h=h, lat=lat,
                extra={k: e.get(k) for k in ("closed", "active", "endDate", "gameStatus", "status") if k in e})
            st["late"] = is_late(e)
            if e.get("ended") and not st["final_seen"]: st["final_seen"] = time.time()
            if m.get("closed") or m.get("status") not in (None, "MARKET_STATUS_OPEN"):
                st["closed_seen"] = st["closed_seen"] or time.time()
        if st.get("late"):
            if st["late"] is True: hot_leagues.add(st["lg"])
            b, h, lat = get(G + "/v1/markets/" + st["ml"] + "/book")
            if b is not None:
                if first_book_keys: log("bookraw", slug=slug, raw=json.dumps(b)[:4000]); first_book_keys = False
                log("book", slug=slug, lg=st["lg"], h=h, lat=lat, **book_summary(b))
            else:
                log("book", slug=slug, lg=st["lg"], h=h, lat=lat)
        if st["final_seen"] and time.time() - st["final_seen"] > 40 * 60: st["done"] = True
        if st["closed_seen"] and time.time() - st["closed_seen"] > 5 * 60: st["done"] = True
    for lg in hot_leagues:
        if time.time() < next_feeds.get(lg, 0): continue
        next_feeds[lg] = time.time() + 5
        if lg in LEAGUES:
            d, h, lat = get(f"https://site.api.espn.com/apis/site/v2/sports/{LEAGUES[lg]}/scoreboard", bust=False)
            comps = []
            for ev in (d or {}).get("events", []):
                c = ev["competitions"][0]; stt = c.get("status") or ev.get("status") or {}
                comps.append({"id": ev.get("id"), "name": ev.get("shortName"), "state": stt.get("type", {}).get("state"),
                              "tname": stt.get("type", {}).get("name"), "completed": stt.get("type", {}).get("completed"),
                              "clock": stt.get("displayClock"), "period": stt.get("period"),
                              "score": [t.get("score") for t in c.get("competitors", [])],
                              "teams": [t.get("team", {}).get("abbreviation") for t in c.get("competitors", [])]})
            log("espn", lg=lg, h=h, lat=lat, comps=[x for x in comps if x["state"] == "in" or x["completed"]])
        if lg == "nba":
            d, h, lat = get("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", bust=False)
            gs = [{"id": g.get("gameId"), "code": g.get("gameCode"), "status": g.get("gameStatus"), "txt": g.get("gameStatusText"),
                   "clock": g.get("gameClock"), "period": g.get("period"), "h": (g.get("homeTeam") or {}).get("score"),
                   "a": (g.get("awayTeam") or {}).get("score")} for g in ((d or {}).get("scoreboard") or {}).get("games", [])]
            log("nbacdn", h=h, lat=lat, games=[g for g in gs if g["status"] in (2, 3)])
        if lg == "nhl":
            d, h, lat = get("https://api-web.nhle.com/v1/score/now", bust=False)
            gs = [{"id": g.get("id"), "state": g.get("gameState"), "sched": g.get("gameScheduleState"),
                   "a": (g.get("awayTeam") or {}).get("abbrev"), "h": (g.get("homeTeam") or {}).get("abbrev"),
                   "as": (g.get("awayTeam") or {}).get("score"), "hs": (g.get("homeTeam") or {}).get("score"),
                   "period": (g.get("periodDescriptor") or {}).get("number"), "clock": (g.get("clock") or {}).get("timeRemaining"),
                   "inter": (g.get("clock") or {}).get("inIntermission")} for g in (d or {}).get("games", [])]
            log("nhlapi", h=h, lat=lat, games=[g for g in gs if g["state"] not in ("FUT", "PRE")])
        if lg == "mlb":
            day = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%Y-%m-%d")
            d, h, lat = get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={day}&hydrate=linescore", bust=False)
            gs = []
            for dd in (d or {}).get("dates", []):
                for g in dd.get("games", []):
                    gs.append({"pk": g.get("gamePk"), "abs": g["status"].get("abstractGameState"), "det": g["status"].get("detailedState"),
                               "inn": (g.get("linescore") or {}).get("currentInning"), "half": (g.get("linescore") or {}).get("inningHalf"),
                               "outs": (g.get("linescore") or {}).get("outs"),
                               "teams": [g["teams"]["away"]["team"].get("name"), g["teams"]["home"]["team"].get("name")],
                               "score": [g["teams"]["away"].get("score"), g["teams"]["home"].get("score")]})
            log("mlbapi", h=h, lat=lat, games=gs)
    if not any(st.get("late") for st in tracked.values() if not st["done"]): time.sleep(3)
    else: time.sleep(0.5)
log("end")
