"""NFL staging: nflverse raw files to point-in-time team-game tables.

Step 1 of `docs/MODEL_PLAN_NFL.md`. The college staging's conventions hold
throughout - a home-oriented closing spread that is negative when the home
side is favoured, ``season_type`` of ``regular`` or ``postseason``, kickoffs
in UTC, integer team ids that follow a franchise through a relocation - so
the model modules in :mod:`atlas.models` read an NFL frame exactly as they
read a college one. The point-in-time and opponent-adjustment machinery is
the college code, imported, not copied.
"""
