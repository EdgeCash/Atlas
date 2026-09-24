# College: who records a stat

`atlas/dfs/cfb_participation.py`, step 5 of `docs/MODEL_PLAN_DFS_CFB.md`. A team's candidates for a game are the players who recorded a stat for it in any of its previous eight games; the model reads their recent appearances, career, scoring, position and the point in the season. Walk-forward, 2016-2026, 444,474 candidate-games.

- Brier score 0.133, against 0.174 for his share of the team's last four games (lower is better).
- A priced player with no record for his team - a freshman, or a transfer before his first game - gets a flat 30%, a stated guess: the record cannot measure him.

Predicted against observed, by tenths of the prediction:

| listings | predicted | observed |
|---|---|---|
| 99730 | 5.9% | 3.9% |
| 62881 | 14.2% | 12.6% |
| 36122 | 24.8% | 24.2% |
| 33266 | 35.0% | 34.8% |
| 33775 | 45.1% | 43.4% |
| 30483 | 54.7% | 53.5% |
| 22762 | 64.9% | 62.6% |
| 25329 | 75.4% | 74.2% |
| 39638 | 85.6% | 85.6% |
| 60488 | 93.8% | 93.9% |
