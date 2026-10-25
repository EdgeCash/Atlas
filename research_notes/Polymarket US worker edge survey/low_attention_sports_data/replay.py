"""Replay the favorites rule and measure tape behaviour on low-attention leagues. Read-only on the repo
except the module's own history cache (gitignored)."""
import json, sys, time, math
from pathlib import Path
import pandas as pd
sys.path.insert(0, '/home/user/Atlas')
from atlas.polymarket import backtest as b, source
from atlas.util import session

OUT = Path('/tmp/claude-0/-home-user-Atlas/8739734e-beef-5b53-b4a5-62b091fed4fa/scratchpad/out')
def tape_stats(g, h):
    start = pd.Timestamp(g['start']); fin = g.get('finished')
    end = b.game_end(h, start, fin)
    t = h.assign(long=pd.to_numeric(h['long'], errors='coerce'), short=pd.to_numeric(h['short'], errors='coerce'))
    t = t.dropna(subset=['at']).sort_values('at').set_index('at')
    t = t[~t.index.duplicated(keep='last')]
    t['spread'] = (t['long'] + t['short'] - 1.0)
    pre = t[(t.index < start)]
    live = t[(t.index >= start) & (t.index < end)]
    nonterm = live[~b.terminal(live['long'])]
    res = float(g['result_long']); won_long = res >= 0.999
    wcol = 'long' if won_long else 'short'
    r = {'league': g['league'], 'event_id': g['event_id'], 'event_slug': g['event_slug'], 'start': start, 'end': end,
         'finished_known': pd.notna(fin), 'length_min': (end - start).total_seconds() / 60,
         'n_pre': len(pre), 'n_live': len(live), 'n_live_nonterm': len(nonterm),
         'pre_spread_med': pre['spread'].median() if len(pre) else float('nan'),
         'live_spread_med': nonterm['spread'].median() if len(nonterm) else float('nan'),
         'live_spread_p90': nonterm['spread'].quantile(0.9) if len(nonterm) else float('nan'),
         'live_tight_frac': float((nonterm['spread'] <= 0.04).mean()) if len(nonterm) else float('nan'),
         'live_wide_frac': float((nonterm['spread'] > 0.10).mean()) if len(nonterm) else float('nan'),
         'long_at_start': pre['long'].iloc[-1] if len(pre) else float('nan'),
         'short_at_start': pre['short'].iloc[-1] if len(pre) else float('nan'),
         'long_2h': pre['long'].iloc[0] if len(pre) else float('nan'),
         'short_2h': pre['short'].iloc[0] if len(pre) else float('nan'),
         'spread_at_start': pre['spread'].iloc[-1] if len(pre) else float('nan'),
         'result_long': res}
    if len(nonterm) >= 2:
        gaps = nonterm.index.to_series().diff().dt.total_seconds().div(60).iloc[1:]
        chg = (nonterm['long'].diff().abs() > 1e-9).iloc[1:]
        r['live_minutes_span'] = float(gaps.sum()); r['live_changes'] = int(chg.sum())
        r['change_per_min'] = float(chg.sum() / gaps.sum()) if gaps.sum() > 0 else float('nan')
        r['median_gap_min'] = float(gaps.median())
        # minutes a change persists: mean run length of unchanged price in minutes
        w = nonterm[wcol]
        # final contiguous run (ending at last nonterminal minute) where winner ask >= 0.95
        arr = (w >= 0.95).values[::-1]
        run = 0
        for v in arr:
            if v: run += 1
            else: break
        r['winner_final_run_ge95_min'] = run
        arr = (w >= 0.90).values[::-1]
        run = 0
        for v in arr:
            if v: run += 1
            else: break
        r['winner_final_run_ge90_min'] = run
        r['winner_ask_last'] = float(w.iloc[-1]); r['winner_spread_last'] = float(nonterm['spread'].iloc[-1])
        # minutes from last change of any price to the end of the nonterminal tape
        ch_idx = nonterm.index[(nonterm['long'].diff().abs() > 1e-9) | (nonterm['short'].diff().abs() > 1e-9)]
        r['last_change_to_end_min'] = (nonterm.index[-1] - ch_idx[-1]).total_seconds() / 60 if len(ch_idx) else float('nan')
        # terminal gap: minutes from last nonterminal minute to the first terminal minute
        term = live[b.terminal(live['long'])]
        r['nonterm_to_terminal_min'] = (term.index[0] - nonterm.index[-1]).total_seconds()/60 if len(term) else float('nan')
        # loser ask max in final 10 nonterminal minutes (a stale favourite?)
        lcol = 'short' if won_long else 'long'
        r['loser_ask_max_last10'] = float(nonterm[lcol].iloc[-10:].max())
        r['loser_ask_ge90_minutes'] = int((nonterm[lcol] >= 0.90).sum())
    return r


if __name__ == '__main__':
    tag = sys.argv[1]; LIMIT = int(sys.argv[2]); LEAGUES = sys.argv[3].split(',')
    log = open(OUT / f'{tag}.log', 'a')
    def say(*a):
        print(*a, file=log, flush=True)
    
    evs = json.load(open('/home/user/Atlas/data/raw/polymarket_us/closed_events.json'))['events']
    gs_all = b.games(evs, LEAGUES)
    gs = gs_all.groupby('league').tail(LIMIT).reset_index(drop=True)
    say('games per league (all / sampled):', gs_all['league'].value_counts().to_dict(), gs['league'].value_counts().to_dict())
    gs.to_csv(OUT / f'{tag}_games.csv', index=False)
    sess = session()
    pos_rows, tape_rows = [], []
    cache = b.raw_dir() / 'history'
    
    t0 = time.time(); n_fail = 0; n_empty = 0
    for i, g in enumerate(gs.to_dict('records'), 1):
        try:
            h = b.history(str(g['market_slug']), g['start'], g['finished'], sess, cache_dir=cache)
        except Exception as e:
            n_fail += 1; say('fail', g['market_slug'], type(e).__name__, e); time.sleep(0.5); continue
        if h.empty:
            n_empty += 1; continue
        try:
            pos_rows.extend(b.crossings(g, h))
            tape_rows.append(tape_stats(g, h))
        except Exception as e:
            say('calc fail', g['market_slug'], type(e).__name__, e)
        if i % 100 == 0:
            say(f'{i}/{len(gs)} {time.time()-t0:.0f}s pos={len(pos_rows)} fail={n_fail} empty={n_empty}')
            pd.DataFrame(pos_rows, columns=b.POSITION_COLUMNS).to_csv(OUT / f'{tag}_positions.csv', index=False)
            pd.DataFrame(tape_rows).to_csv(OUT / f'{tag}_tape.csv', index=False)
        time.sleep(source.PAUSE)
    pd.DataFrame(pos_rows, columns=b.POSITION_COLUMNS).to_csv(OUT / f'{tag}_positions.csv', index=False)
    pd.DataFrame(tape_rows).to_csv(OUT / f'{tag}_tape.csv', index=False)
    say(f'DONE {len(gs)} games {time.time()-t0:.0f}s pos={len(pos_rows)} fail={n_fail} empty={n_empty}')
