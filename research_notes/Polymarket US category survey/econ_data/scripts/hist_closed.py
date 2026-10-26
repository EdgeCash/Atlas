import json,time,urllib.request,urllib.error,datetime as dt,sys
ev=json.load(open('raw/closed_econ.json'))
# release instants (UTC) per event
T={'uscpi-may2026yoy-2026-06-10':'2026-06-10T12:30','usfed-fomc-2026-06-17':'2026-06-17T18:00','uschange-gte-june-2026-07-02':'2026-07-02T12:30',
'us-seasonadj-gte-june-2026-07-02':'2026-07-02T12:30','uscpi-june-yoy-2026-07-14':'2026-07-14T12:30','usfed-fomc-2026-07-29':'2026-07-29T18:00',
'us-saa-q2-2026-07-30':'2026-07-30T12:30','uscpi-july-yoy-2026-08-12':'2026-08-12T12:30','usnfp-sa-july-2026-08-07':'2026-08-07T12:30',
'usunemp-sa-july-2026-08-07':'2026-08-07T12:30','usunemp-sa-august-2026-09-04':'2026-09-04T12:30','usnfp-sa-august-2026-09-04':'2026-09-04T12:30',
'uscpi-august-yoy-2026-09-11':'2026-09-11T12:30','usfed-fomc-2026-09-16':'2026-09-16T18:00','usnfp-sa-september-2026-10-02':'2026-10-02T12:30',
'usunemp-sa-september-2026-10-02':'2026-10-02T12:30','uscpi-september-mom-2026-10-14':'2026-10-14T12:30','uscpi-september-yoy-2026-10-14':'2026-10-14T12:30',
'uscpicore-september-yoy-2026-10-14':'2026-10-14T12:30','uscpicore-september-mom-2026-10-14':'2026-10-14T12:30',
'ecb-2026-09-10':'2026-09-10T12:15','boe-2026-09-17':'2026-09-17T11:00','boc-2026-09-02':'2026-09-02T13:45','bcb-2026-09-16':'2026-09-16T21:30',
'boj-2026-09-18':'2026-09-18T03:00','cbr-2026-10-23':'2026-10-23T10:30','boi-2026-10-21':'2026-10-21T13:00','banxico-2026-09-24':'2026-09-24T19:00',
'boe-2026-07-30':'2026-07-30T11:00','bcb-2026-08-05':'2026-08-05T21:30','umcsent-2026-09-25':'2026-09-25T14:00'}
def get(url):
    for a in range(6):
        try:
            with urllib.request.urlopen(url,timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(a+1)); continue
            return {'err':e.code}
        except Exception as e: time.sleep(2)
    return {'err':'fail'}
out={}
for e in ev:
    if e['slug'] not in T: continue
    t0=dt.datetime.fromisoformat(T[e['slug']]+':00+00:00')
    st=int((t0-dt.timedelta(minutes=120)).timestamp()); en=int((t0+dt.timedelta(minutes=240)).timestamp())
    for m in e['markets']:
        d=get(f"https://gateway.polymarket.us/v1/price-history?symbol={m['slug']}&timestamp.startTimestamp={st}&timestamp.endTimestamp={en}&fidelity=1")
        out[m['slug']]={'event':e['slug'],'T':T[e['slug']],'title':m.get('title'),'settle':m.get('outcomePrices'),'resolved_at':m.get('endDate'),'h':d.get('history',[]),'err':d.get('err')}
        time.sleep(0.5)
    print(e['slug'],file=sys.stderr)
json.dump(out,open('raw/closed_hist_1m.json','w'))
