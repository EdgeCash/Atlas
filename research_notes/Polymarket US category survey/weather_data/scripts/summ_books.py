import json, sys
r = json.load(open(sys.argv[1])); print(r["ts"])
for s, v in r["books"].items():
    md = v["book"].get("marketData", {})
    bids = md.get("bids", []); offs = md.get("offers", [])
    bb = float(bids[0]["px"]["value"]) if bids else None
    ba = float(offs[0]["px"]["value"]) if offs else None
    def depth(levels, ref, side, w=0.05):
        if ref is None: return 0
        return sum(float(l["qty"]) for l in levels if abs(float(l["px"]["value"]) - ref) <= w + 1e-9)
    st = md.get("stats", {})
    bd = sum(float(l["qty"]) for l in bids); ad = sum(float(l["qty"]) for l in offs)
    top_b = float(bids[0]["qty"]) if bids else 0; top_a = float(offs[0]["qty"]) if offs else 0
    print(f"{s:48s} {v['title'][:12]:12s} bid {bb} x{top_b:.0f} ask {ba} x{top_a:.0f} | $ask5c {sum(float(l['qty'])*float(l['px']['value']) for l in offs if ba and float(l['px']['value'])<=ba+0.05):.0f} | traded {st.get('sharesTraded')} notional {st.get('notionalTraded',{}).get('value')} OI {st.get('openInterest')} last {st.get('lastTradeSetTime','')[:19]}")
