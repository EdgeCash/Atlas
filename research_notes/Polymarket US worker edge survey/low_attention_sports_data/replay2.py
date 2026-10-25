"""Same as replay.py but fetches each event in full from the gateway, because the slimmed cache dropped the
``*_match_winner`` moneylines (tennis, table tennis, soccer, esports, darts, cricket)."""
import json, sys, time, math
from pathlib import Path
import pandas as pd
sys.path.insert(0, '/home/user/Atlas')
sys.path.insert(0, '/tmp/claude-0/-home-user-Atlas/8739734e-beef-5b53-b4a5-62b091fed4fa/scratchpad/work')
from atlas.polymarket import backtest as b, source
from atlas.util import session
from replay import tape_stats, OUT  # noqa  (replay.py only runs its loop when given argv; guard below)

tag = sys.argv[1]; LIMIT = int(sys.argv[2]); LEAGUES = sys.argv[3].split(',')
log = open(OUT / f'{tag}.log', 'a')
def say(*a): print(*a, file=log, flush=True)

evs = json.load(open('/home/user/Atlas/data/raw/polymarket_us/closed_events.json'))['events']
rows = []
for e in evs:
    lg = b.league_of(e)
    if lg in LEAGUES and len(e.get('teams') or []) == 2:
        rows.append({'league': lg, 'id': str(e['id']), 'slug': e.get('slug'), 'start': source._utc(e.get('startTime') or e.get('startDate')),
                     'finished': source._utc(e.get('finishedTimestamp') or e.get('closedTime'))})
df = pd.DataFrame(rows).dropna(subset=['start']).sort_values('start')
df = df.groupby('league').tail(LIMIT).reset_index(drop=True)
say('sampled:', df['league'].value_counts().to_dict())
sess = session(); cache = b.raw_dir() / 'history'
pos_rows, tape_rows, meta_rows = [], [], []
t0 = time.time(); nf = 0; ne = 0

def pick_markets(ev):
    ms = ev.get('markets') or []
    want = 'aec-' + str(ev.get('slug'))
    for m in ms:
        if m.get('slug') == want: return [m]
    out = [m for m in ms if str(m.get('sportsMarketType') or '') == 'moneyline' or str(m.get('sportsMarketType') or '').endswith(('_match_winner', '_full_game_winner'))]
    if out: return out[:1]
    three = [m for m in ms if str(m.get('sportsMarketType') or '').endswith('_full_time_winner') or str(m.get('sportsMarketType') or '') == 'drawable_outcome']
    keep = [m for m in three if 'draw' not in str(m.get('question') or '').lower() and 'draw' not in str(m.get('slug') or '').lower()]
    return keep[:2] if keep else three[:2]

for i, r in enumerate(df.to_dict('records'), 1):
    try:
        ev = source._get(f"/v1/events/{r['id']}", None, sess).get('event') or {}
    except Exception as ex:
        nf += 1; say('event fail', r['slug'], type(ex).__name__); time.sleep(0.3); continue
    mlist = pick_markets(ev)
    if not mlist:
        ne += 1; say('no market', r['slug'], [x.get('sportsMarketType') for x in ev.get('markets') or []][:6]); continue
    for m in mlist:
      sides = m.get('marketSides') or []
      long_ = next((s for s in sides if s.get('long', False)), sides[0] if sides else {})
      try: res = float(long_.get('price'))
      except (TypeError, ValueError): res = float('nan')
      g = {'league': r['league'], 'event_id': r['id'], 'event_slug': r['slug'], 'label': ev.get('title'), 'away': '', 'home': '',
           'start': r['start'], 'finished': r['finished'] if pd.notna(r['finished']) else pd.NaT, 'market_slug': m.get('slug'),
           'fee_rate': source.fee_rate(m), 'long_side': 'away', 'result_long': res}
      meta_rows.append({**g, 'market_type': m.get('sportsMarketType'), 'score': ev.get('score'), 'volume': m.get('volume'),
                        'liquidity': m.get('liquidity'), 'created': m.get('createdAt'), 'n_markets': len(ev.get('markets') or [])})
      try:
          h = b.history(str(g['market_slug']), g['start'], g['finished'], sess, cache_dir=cache)
      except Exception as ex:
          nf += 1; say('hist fail', g['market_slug'], type(ex).__name__); time.sleep(0.3); continue
      if h.empty:
          ne += 1; continue
      try:
          pos_rows.extend(b.crossings(g, h)); tape_rows.append(tape_stats(g, h))
      except Exception as ex:
          say('calc fail', g['market_slug'], type(ex).__name__, ex)
    if i % 100 == 0:
        say(f'{i}/{len(df)} {time.time()-t0:.0f}s pos={len(pos_rows)} fail={nf} empty/nomarket={ne}')
        pd.DataFrame(pos_rows, columns=b.POSITION_COLUMNS).to_csv(OUT / f'{tag}_positions.csv', index=False)
        pd.DataFrame(tape_rows).to_csv(OUT / f'{tag}_tape.csv', index=False)
        pd.DataFrame(meta_rows).to_csv(OUT / f'{tag}_meta.csv', index=False)
    time.sleep(source.PAUSE)
pd.DataFrame(pos_rows, columns=b.POSITION_COLUMNS).to_csv(OUT / f'{tag}_positions.csv', index=False)
pd.DataFrame(tape_rows).to_csv(OUT / f'{tag}_tape.csv', index=False)
pd.DataFrame(meta_rows).to_csv(OUT / f'{tag}_meta.csv', index=False)
say(f'DONE {len(df)} {time.time()-t0:.0f}s pos={len(pos_rows)} fail={nf} empty/nomarket={ne}')
