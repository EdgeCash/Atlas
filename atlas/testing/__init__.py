"""Deterministic fixtures. Importable from the package so CI exercises the
same code paths as a real build, without touching the network."""

from atlas.testing.synthetic import write_synthetic_raw

__all__ = ["write_synthetic_raw"]
