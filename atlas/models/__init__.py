"""Score-distribution models and the harness that grades them.

`docs/MODEL_FOUNDATION.md` sets the goal: a calibrated joint distribution over
the final score, per game, with the projection read off it as a decimal mean.
This package holds what every model shares - proper scoring rules, the
key-number lattice, the reference models every candidate is scored beside -
and, per sport, the benchmark reports and the models themselves.

Nothing here reads the market as an input to a model. The market appears only
as one of the references a model is compared against.
"""
