import json,time,sys,os
sys.path.insert(0,os.path.dirname(__file__))
from common import get,G
OUT=sys.argv[1]
PFX=('btc-above-day','btc-above-wk','btc-hit-','btc-100k','btc-150k','btc-above-yr','btc-hitprice','btc-pricerange-yr','btc-above-hr','btc-range-day','btc-range-wk',
     'eth-above-day','eth-above-wk','eth-hit-','eth-above-hr')
t0=time.time()
snap={'t_start':t0}
lst=get(G+'/v1/events?closed=false&limit=500&offset=0&categories=crypto')
snap['coinbase']={p:get(f'https://api.exchange.coinbase.com/products/{p}/ticker',gateway=False) for p in ('BTC-USD','ETH-USD')}
snap['brti']=get(G+f'/v1/asset-prices/history?assets=crypto:btc&assets=crypto:eth&from={int(t0)-120}&to=0&bucket=ASSET_PRICE_BUCKET_1S')
for c in ('BTC','ETH'):
    snap['deribit_'+c]=get(f'https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={c}&kind=option',gateway=False)
    snap['deribit_fut_'+c]=get(f'https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={c}&kind=future',gateway=False)
mk=[]
for e in lst['events']:
    if e['slug'].startswith(PFX):
        for m in e['markets']:
            mk.append({'event':e['slug'],'slug':m['slug'],'endDate':m['endDate'],'createdAt':m.get('createdAt'),'apt':{k:v for k,v in (m.get('assetPriceTerms') or {}).items() if k!='chart'},
                       'desc':m['description'][:400],'fee':m.get('feeCoefficient'),'tick':m.get('orderPriceMinTickSize')})
snap['markets']=mk
for m in mk:
    b=get(G+f"/v1/markets/{m['slug']}/book")
    md=(b or {}).get('marketData') or {}
    m['t']=time.time()
    m['bids']=[(float(x['px']['value']),float(x['qty'])) for x in md.get('bids',[])]
    m['offers']=[(float(x['px']['value']),float(x['qty'])) for x in md.get('offers',[])]
    st=md.get('stats') or {}
    m['traded']=st.get('sharesTraded');m['notional']=(st.get('notionalTraded') or {}).get('value');m['oi']=st.get('openInterest');m['lastTradeTime']=st.get('lastTradeSetTime');m['state']=md.get('state')
snap['coinbase_end']={p:get(f'https://api.exchange.coinbase.com/products/{p}/ticker',gateway=False) for p in ('BTC-USD','ETH-USD')}
snap['t_end']=time.time()
snap['brti_window']=get(G+f"/v1/asset-prices/history?assets=crypto:btc&assets=crypto:eth&from={int(t0)-60}&to={int(snap['t_end'])+1}&bucket=ASSET_PRICE_BUCKET_1S")
json.dump(snap,open(OUT,'w'))
print(OUT,len(mk),round(snap['t_end']-t0))
