"""NHL staging: the NHL's raw files to point-in-time game, team-game, goalie-game and shot tables.

Step 1 of `docs/MODEL_PLAN_NHL.md`. The conventions the live and site
layers read hold here as they do for football - kickoffs in UTC, a
home-oriented ``actual_margin`` and ``actual_total``, ``season_type`` of
``regular`` or ``postseason``, integer team ids that follow a franchise
through a relocation - and the rest is hockey's own: the regulation score
beside the final, how the game was decided, rest, and every shot attempt
with its geometry and strength state.
"""
