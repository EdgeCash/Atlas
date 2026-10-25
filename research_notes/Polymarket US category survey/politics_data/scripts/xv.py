import sys,json,time,urllib.request,urllib.parse
rows=json.load(open("../raw/bbo_rows.json"))
evs={e["slug"]:e for e in json.load(open("../raw/nonmid_open.json"))}
def gget(u):
    for i in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"research"}),timeout=60).read())
        except Exception as e: time.sleep(3)
skip={"extpl","usrrc","ussupct","usterr","intlcombo","ref","spapm","srbpm","trumpapprove","trmpapprv","swepm"}
out={}
for slug,e in evs.items():
    if slug.split("-")[0] in skip: continue
    q=e["title"].replace("?","")
    d=gget("https://gamma-api.polymarket.com/public-search?"+urllib.parse.urlencode({"q":q,"limit_per_type":3,"events_status":"active"}))
    cands=[x for x in (d or {}).get("events",[]) if not x.get("closed")]
    out[slug]={"q":q,"cands":[{"slug":c["slug"],"title":c["title"],"volume":c.get("volume"),"markets":[{"q":m.get("question"),"git":m.get("groupItemTitle"),"bid":m.get("bestBid"),"ask":m.get("bestAsk"),"last":m.get("lastTradePrice"),"closed":m.get("closed"),"tok":m.get("clobTokenIds"),"end":m.get("endDate")} for m in c.get("markets",[])]} for c in cands[:3]]}
    print(slug,"->",[(c["slug"],c["title"]) for c in cands[:3]],flush=True)
    time.sleep(0.6)
json.dump(out,open("../raw/xv_gamma.json","w"))
