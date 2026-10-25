import json,re,unicodedata
rows=json.load(open("../raw/bbo_rows.json")); G=json.load(open("../raw/xv_gamma.json"))
def norm(s): return unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()
months=["january","february","march","april","may","june","july","august","september","october","november","december"]
def key_date(s):
    s=norm(s); m=re.search(r"(%s)\s+(\d+)"%"|".join(months),s); y=re.search(r"20\d\d",s)
    return (m.group(1),m.group(2)) if m else None
res=[]
for r in rows:
    if r["ev"] not in G: continue
    t=norm(r["title"]); kd=key_date(r["title"])
    best=None
    for c in G[r["ev"]]["cands"]:
        for m in c["markets"]:
            if m["closed"]: continue
            git=norm(m["git"]); q=norm(m["q"])
            if kd:
                # dated leg: match same month/day in question or git, and event family must match
                if key_date(m["git"] or "")==kd or key_date(m["q"] or "")==kd: best=(c,m)
                if best: break
            else:
                toks=[w for w in re.findall(r"[a-z]+",t) if len(w)>2]
                last=toks[-1] if toks else t
                if "-" in r["title"]: last=[w for w in re.findall(r"[a-z]+",norm(r["title"].split("-")[0])) if len(w)>2][-1]
                if last and (last in git or (not git and last in q)): best=(c,m); break
        if best: break
    if not best: continue
    c,m=best
    try: gb,ga=float(m["bid"]),float(m["ask"])
    except: continue
    if r["bid"] is None or r["ask"] is None: pm=None
    else: pm=(r["bid"]+r["ask"])/2
    res.append(dict(pm_slug=r["slug"],pm_title=r["title"],pm_bid=r["bid"],pm_ask=r["ask"],pm_bs=r["bs"],pm_as=r["as_"],g_event=c["slug"],g_title=m["git"] or m["q"],g_bid=gb,g_ask=ga,gap_mid=(pm-(gb+ga)/2) if pm is not None else None))
json.dump(res,open("../raw/xv_matched.json","w"))
fee=lambda p:0.0695*p*(1-p)
print(len(res))
for x in sorted(res,key=lambda x:-abs(x["gap_mid"] or 0)):
    # executable one-sided edge on PMUS: buy yes if pm_ask+fee < g_bid ; buy no if (1-pm_bid)+fee < 1-g_ask
    e_yes=(x["g_bid"]-x["pm_ask"]-fee(x["pm_ask"])) if x["pm_ask"] else None
    e_no=((1-x["g_ask"])-(1-x["pm_bid"])-fee(1-x["pm_bid"])) if x["pm_bid"] else None
    x["e_yes"],x["e_no"]=e_yes,e_no
    print(f"{x['pm_slug'][:46]:46s} {x['pm_title'][:20]:20s} PM {x['pm_bid']}/{x['pm_ask']} G {x['g_bid']}/{x['g_ask']} [{x['g_title'][:28]}] gap={x['gap_mid'] if x['gap_mid'] is None else round(x['gap_mid'],3)} eYes={None if e_yes is None else round(e_yes,3)} eNo={None if e_no is None else round(e_no,3)}")
json.dump(res,open("../raw/xv_matched.json","w"))
