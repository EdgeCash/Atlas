import json,time,urllib.request,urllib.error,statistics as st,datetime as dt
pairs=[('KXFEDDECISION','KXFEDDECISION-26OCT-H0','rdc-usfed-fomc-2026-10-28-nochng'),
('KXFEDDECISION','KXFEDDECISION-26OCT-H25','rdc-usfed-fomc-2026-10-28-hike25'),
('KXFEDDECISION','KXFEDDECISION-26DEC-H25','rdc-usfed-fomc-2026-12-09-hike25'),
('KXFEDDECISION','KXFEDDECISION-26DEC-H0','rdc-usfed-fomc-2026-12-09-nochng'),
('KXU3','KXU3-26OCT-T4.1','urc-usunemp-sa-october-2026-11-06-gt4pt1pct'),
('KXU3','KXU3-26OCT-T4.2','urc-usunemp-sa-october-2026-11-06-gt4pt2pct'),
('KXPAYROLLS','KXPAYROLLS-26OCT-T50000','nfpc-usnfp-sa-october-2026-11-06-gt50k'),
('KXPAYROLLS','KXPAYROLLS-26OCT-T100000','nfpc-usnfp-sa-october-2026-11-06-gt100k'),
('KXCPI','KXCPI-26OCT-T0.2','cpic-uscpi-october-mom-2026-11-10-gt0pt2pct'),
('KXCPI','KXCPI-26OCT-T0.3','cpic-uscpi-october-mom-2026-11-10-gt0pt3pct'),
('KXCPICORE','KXCPICORE-26OCT-T0.2','cpic-uscpicore-october-mom-2026-11-10-gt0pt2pct'),
('KXCPICORE','KXCPICORE-26OCT-T0.3','cpic-uscpicore-october-mom-2026-11-10-gt0pt3pct'),
('KXGDP','KXGDP-26OCT30-T2.5','gdpc-us-saa-q3-2026-10-29-gt2pt5'),
('KXGDP','KXGDP-26OCT30-T2.0','gdpc-us-saa-q3-2026-10-29-gt2pt0')]
end=int(time.time()); start=end-14*86400
def get(url):
    for a in range(6):
        try: return json.load(urllib.request.urlopen(url,timeout=60))
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(5*(a+1)); continue
            return {'err':e.code}
        except Exception as e: time.sleep(3)
    return {}
res={}
for ser,kt,ps in pairs:
    k=get(f"https://api.elections.kalshi.com/trade-api/v2/series/{ser}/markets/{kt}/candlesticks?start_ts={start}&end_ts={end}&period_interval=60")
    time.sleep(3)
    p=get(f"https://gateway.polymarket.us/v1/price-history?symbol={ps}&fixedInterval=INTERVAL_ALL&fidelity=60")
    time.sleep(0.6)
    res[kt]={'k':k,'p':p,'ps':ps}
json.dump(res,open('raw/xvenue_raw.json','w'))
print('done',[ (kt,len(v['k'].get('candlesticks',[])),len(v['p'].get('history',[]))) for kt,v in res.items()])
