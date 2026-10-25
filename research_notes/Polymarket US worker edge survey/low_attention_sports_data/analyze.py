import pandas as pd, numpy as np, sys, glob, math
sys.path.insert(0,'/home/user/Atlas')
from atlas.polymarket import backtest as b
O='/tmp/claude-0/-home-user-Atlas/8739734e-beef-5b53-b4a5-62b091fed4fa/scratchpad/out/'
pd.set_option('display.width',250); pd.set_option('display.max_rows',1000); pd.set_option('display.max_columns',50)
def load(kind):
    fs = sorted(glob.glob(O+f'*_{kind}.csv'))
    return pd.concat([pd.read_csv(f).assign(src=f.split('/')[-1].split('_')[0]) for f in fs if pd.read_csv(f, nrows=1).shape[0]], ignore_index=True)
pos = load('positions'); tape = load('tape'); meta = load('meta')
pos = pos.drop_duplicates(subset=['event_id','side','long','phase','threshold'], keep='last')
tape = tape.drop_duplicates(subset=['event_id'], keep='last')
# knowable match-length caps (minutes after start) - manual, by league
CAP = {'atp':180,'wta':180,'atpcq':180,'itfme':150,'itfwo':150,'itfm':150,'itfw':150,'utr':120,
       'setkameua':40,'setkamecz':40,'setkamemd':40,'setkawoua':40,'wtt':45,'ttelite':40,'ttcup':40,
       'cs2':150,'lol':150,'dota2':180,'valorant':150,
       'epl':120,'lal':120,'lg1':120,'ucl':120,'arg2':120,'j2':120,'czechligapro':120,'engnl':120,'eflch':120,
       'ebfsa':25,'ebfpl':25,'ebb':25,'ebbec':25,'eurolg':120,'mlb':210,'npb':220,'ahl':170,'khl':170,'nhl':170,'nba':165,'nfl':210,
       'ufc':40,'boxing':60,'pdcdarts':60,'modus':40,'t20icr':220,'ipl':240}
pos['cap'] = pos['league'].map(CAP)
pos['window'] = np.where(pos.phase=='pregame','pregame', np.where(pos.minutes_in<=pos.cap, 'in_match', 'dead_book'))
GROUP = {'atp':'tennis_tour','wta':'tennis_tour','atpcq':'tennis_tour','itfme':'itf','itfwo':'itf','itfm':'itf','itfw':'itf','utr':'utr',
 'setkameua':'table_tennis','setkamecz':'table_tennis','setkamemd':'table_tennis','setkawoua':'table_tennis','wtt':'table_tennis_wtt','ttelite':'table_tennis','ttcup':'table_tennis',
 'cs2':'esports','lol':'esports','dota2':'esports','valorant':'esports','epl':'soccer_top','lal':'soccer_top','lg1':'soccer_top','ucl':'soccer_top',
 'arg2':'soccer_low','j2':'soccer_low','czechligapro':'table_tennis','engnl':'soccer_low','eflch':'soccer_low','ebfsa':'ebattles','ebfpl':'ebattles','ebb':'ebattles','ebbec':'ebattles',
 'eurolg':'eurolg','mlb':'mlb','npb':'npb','ahl':'hockey_minor','khl':'hockey_minor','nhl':'majors','nba':'majors','nfl':'majors','ufc':'combat','boxing':'combat','pdcdarts':'darts','modus':'darts','t20icr':'cricket','ipl':'cricket'}
pos['group'] = pos.league.map(GROUP); tape['group'] = tape.league.map(GROUP)
tight = pos[pos.spread<=0.04]
print("### positions by league/window"); print(pos.groupby(['league','window']).size().unstack(fill_value=0).to_string())
print("\n### fee rates by league (from full-event fetch)"); 
if len(meta): print(meta.groupby('league')['fee_rate'].agg(lambda x: x.value_counts().to_dict()).to_string())
def tab(df, by, latency=None):
    return b.summary(df, by=by, latency=latency)
print("\n### IN MATCH, tight book, ideal fill at the trigger ask, by group x threshold")
print(tab(tight[tight.window=='in_match'], ('group','threshold')).round(3).to_string())
print("\n### IN MATCH, tight book, by league x threshold (0.85/0.90/0.95)")
s = tab(tight[tight.window=='in_match'], ('league','threshold')); print(s[s.threshold.isin([0.85,0.9,0.95])].round(3).to_string())
print("\n### IN MATCH, tight book, stale-limit fill 1 minute late (the 45-s poller), by group x threshold")
print(tab(tight[tight.window=='in_match'], ('group','threshold'), latency=1).round(3).to_string())
print("\n### IN MATCH, tight book, 5 minutes late"); print(tab(tight[tight.window=='in_match'], ('group','threshold'), latency=5).round(3).to_string())
print("\n### IN MATCH late phase (minutes_in >= 0.6*cap), tight, by group"); 
late = tight[(tight.window=='in_match') & (tight.minutes_in >= 0.6*tight.cap)]
print(tab(late, ('group','threshold')).round(3).to_string())
print("\n### DEAD BOOK (minutes_in > cap, market unsettled), any spread, by group x threshold")
print(tab(pos[pos.window=='dead_book'], ('group','threshold')).round(3).to_string())
print("\n### DEAD BOOK tight"); print(tab(tight[tight.window=='dead_book'], ('group','threshold')).round(3).to_string())
print("\n### PREGAME crossings, tight, by group x threshold"); print(tab(tight[tight.window=='pregame'], ('group','threshold')).round(3).to_string())
# pregame calibration from price at start
t = tape.copy()
rows=[]
for side in ('long','short'):
    px = t[f'{side}_at_start']; won = (t.result_long>=0.999) if side=='long' else (t.result_long<=0.001)
    settled = t.result_long.isin([0.0,1.0])
    d = pd.DataFrame({'group':t.group,'league':t.league,'px':px,'won':won.astype(float),'settled':settled, 'spread':t.spread_at_start})
    rows.append(d)
cal = pd.concat(rows); cal = cal[cal.settled & cal.px.notna() & (cal.spread<=0.06)]
cal['bucket'] = pd.cut(cal.px, [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,0.98,1.0])
cal['fee'] = 0.0695*cal.px*(1-cal.px)
cal['cost'] = cal.px+cal.fee
g = cal.groupby(['group','bucket'], observed=True).agg(n=('won','size'), win=('won','mean'), cost=('cost','mean')).reset_index()
g['edge'] = g.win-g.cost; g['se'] = np.sqrt(g.win*(1-g.win)/g.n)
print("\n### PREGAME calibration at the start price (ask), spread<=6c, fee 0.0695"); print(g.round(3).to_string())
print("\n### Pregame move in last 2h: median |ask_start - ask_2h| by league, and share of games with any pregame tape")
t['move'] = (t.long_at_start - t.long_2h).abs()
print(t.groupby('league').agg(n=('event_id','size'), move_med=('move','median'), move_p90=('move', lambda x: x.quantile(.9)), pre_spread=('pre_spread_med','median'), spread_start=('spread_at_start','median'), n_pre_med=('n_pre','median')).round(3).to_string())
print("\n### TAPE stats by league")
tp = t.groupby('league').agg(n=('event_id','size'), finished_known=('finished_known','mean'), len_med=('length_min','median'), live_spread=('live_spread_med','median'), live_p90=('live_spread_p90','median'),
  tight_frac=('live_tight_frac','median'), wide_frac=('live_wide_frac','median'), chg_per_min=('change_per_min','median'), chg_p25=('change_per_min', lambda x: x.quantile(.25)),
  run95_med=('winner_final_run_ge95_min','median'), run95_p75=('winner_final_run_ge95_min', lambda x: x.quantile(.75)), settle_gap=('nonterm_to_terminal_min','median'),
  no_terminal=('nonterm_to_terminal_min', lambda x: x.isna().mean()), loser90_min=('loser_ask_ge90_minutes','median'))
print(tp.round(3).to_string())
tape.to_csv(O+'ALL_tape.csv', index=False); pos.to_csv(O+'ALL_positions.csv', index=False)
