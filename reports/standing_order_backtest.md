# Standing orders late in games, on Polymarket US's own tape

*Built 2026-10-24 23:01 UTC by `python -m atlas.polymarket.standing`. The rule and the test were fixed first, in [`docs/STANDING_ORDER_PREREGISTRATION.md`](../docs/STANDING_ORDER_PREREGISTRATION.md).*

Late in a game, the first minute a side's ask reaches the threshold on a book inside 4¢, a buy limit is posted some cents under that ask for a few minutes. It fills at its own price when the ask falls below it, and is graded by the venue's settlement. Late is elapsed time against the league's median game length, which is knowable during the game:

| League | Late from (minutes after the start) |
|---|---|
| CBB | 113 |
| CFB | 193 |
| NBA | 136 |
| NFL | 173 |
| NHL | 150 |

## The pre-registered test

85¢, 3¢ under the ask, resting 5 minutes, filled only when the ask goes below it, paying the taker fee. **Not established.**

| | |
|---|---|
| Orders posted | 5431 |
| Filled | 1327 (24.4%) |
| Win rate | 81.0% |
| Break-even (mean cost) | 88.8% |
| Edge | -7.8 ± 1.0 points |
| Profit per $ | -8.6% |

| Criterion | Held |
|---|---|
| at least 200 fills | yes |
| edge less 1.96 errors above zero | no |
| edge above zero in both halves | no |

| Half | Triggers from | to | Filled | Edge (pts) |
|---|---|---|---|---|
| first half | 2025-11-03 | 2026-02-04 | 664 | -7.6 ± 1.4 |
| second half | 2026-02-04 | 2026-10-24 | 663 | -8.1 ± 1.5 |

## For comparison: taking the ask at the trigger

The same late triggers, bought at the trigger minute's ask with the taker fee. This is the live favorites rule's late trade, with late defined the same knowable way.

| Threshold | Filled / posted | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|
| 85% | 5431 / 5431 | 93.7% | 93.7% | +0.0 ± 0.3 | 0.1% |
| 90% | 5153 / 5153 | 95.4% | 95.3% | +0.2 ± 0.3 | 0.2% |

## The primary rule by league (exploration)

| League | Threshold | Filled / posted | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| CBB | 85% | 785 / 3175 | 80.9% | 89.0% | -8.1 ± 1.3 | -9.0% |
| CBB | 90% | 656 / 3035 | 84.6% | 91.6% | -7.0 ± 1.3 | -7.5% |
| CFB | 85% | 108 / 365 | 82.4% | 88.2% | -5.8 ± 3.3 | -5.7% |
| CFB | 90% | 85 / 333 | 89.4% | 91.1% | -1.7 ± 3.3 | -0.9% |
| NBA | 85% | 247 / 871 | 81.4% | 88.5% | -7.2 ± 2.4 | -8.1% |
| NBA | 90% | 208 / 825 | 87.0% | 91.5% | -4.5 ± 2.3 | -4.9% |
| NFL | 85% | 66 / 170 | 90.9% | 89.4% | +1.5 ± 3.5 | 3.4% |
| NFL | 90% | 50 / 153 | 94.0% | 91.7% | +2.3 ± 3.4 | 3.6% |
| NHL | 85% | 121 / 850 | 74.4% | 88.8% | -14.4 ± 3.8 | -15.8% |
| NHL | 90% | 114 / 807 | 74.6% | 90.7% | -16.2 ± 4.0 | -17.3% |

## Every cell (exploration)

Each row is a separate rule. With 72 of them, a few will look good by chance; none but the pre-registered one above counts as evidence.

| Threshold | Under the ask | Minutes | Fill | Fee | Filled / posted | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|---|---|---|
| 85% | 1¢ | 3 | through | none | 1549 / 5431 | 84.5% | 90.6% | -6.1 ± 0.9 | -6.5% |
| 85% | 1¢ | 3 | through | taker | 1549 / 5431 | 84.5% | 91.2% | -6.7 ± 0.9 | -7.1% |
| 85% | 1¢ | 3 | touch | none | 1769 / 5431 | 85.9% | 90.9% | -5.0 ± 0.8 | -5.3% |
| 85% | 1¢ | 3 | touch | taker | 1769 / 5431 | 85.9% | 91.4% | -5.6 ± 0.8 | -5.9% |
| 85% | 1¢ | 5 | through | none | 1846 / 5431 | 84.9% | 90.7% | -5.8 ± 0.8 | -6.2% |
| 85% | 1¢ | 5 | through | taker | 1846 / 5431 | 84.9% | 91.3% | -6.4 ± 0.8 | -6.8% |
| 85% | 1¢ | 5 | touch | none | 2067 / 5431 | 86.2% | 91.0% | -4.8 ± 0.7 | -5.1% |
| 85% | 1¢ | 5 | touch | taker | 2067 / 5431 | 86.2% | 91.5% | -5.4 ± 0.7 | -5.7% |
| 85% | 1¢ | 10 | through | none | 2129 / 5431 | 84.8% | 90.8% | -6.0 ± 0.7 | -6.5% |
| 85% | 1¢ | 10 | through | taker | 2129 / 5431 | 84.8% | 91.3% | -6.6 ± 0.7 | -7.0% |
| 85% | 1¢ | 10 | touch | none | 2355 / 5431 | 86.1% | 91.0% | -4.9 ± 0.7 | -5.2% |
| 85% | 1¢ | 10 | touch | taker | 2355 / 5431 | 86.1% | 91.6% | -5.5 ± 0.7 | -5.8% |
| 85% | 3¢ | 3 | through | none | 1042 / 5431 | 80.5% | 88.0% | -7.5 ± 1.2 | -8.2% |
| 85% | 3¢ | 3 | through | taker | 1042 / 5431 | 80.5% | 88.7% | -8.2 ± 1.2 | -9.0% |
| 85% | 3¢ | 3 | touch | none | 1145 / 5431 | 81.9% | 88.1% | -6.2 ± 1.1 | -6.8% |
| 85% | 3¢ | 3 | touch | taker | 1145 / 5431 | 81.9% | 88.8% | -6.9 ± 1.1 | -7.5% |
| 85% | 3¢ | 5 | through | none | 1327 / 5431 | 81.0% | 88.1% | -7.1 ± 1.0 | -7.8% |
| 85% | 3¢ | 5 | through | taker | 1327 / 5431 | 81.0% | 88.8% | -7.8 ± 1.0 | -8.6% |
| 85% | 3¢ | 5 | touch | none | 1432 / 5431 | 82.0% | 88.2% | -6.2 ± 1.0 | -6.9% |
| 85% | 3¢ | 5 | touch | taker | 1432 / 5431 | 82.0% | 88.9% | -7.0 ± 1.0 | -7.6% |
| 85% | 3¢ | 10 | through | none | 1643 / 5431 | 80.8% | 88.3% | -7.6 ± 0.9 | -8.4% |
| 85% | 3¢ | 10 | through | taker | 1643 / 5431 | 80.8% | 89.0% | -8.3 ± 0.9 | -9.1% |
| 85% | 3¢ | 10 | touch | none | 1743 / 5431 | 81.8% | 88.4% | -6.6 ± 0.9 | -7.3% |
| 85% | 3¢ | 10 | touch | taker | 1743 / 5431 | 81.8% | 89.1% | -7.3 ± 0.9 | -8.0% |
| 85% | 5¢ | 3 | through | none | 767 / 5431 | 76.9% | 85.7% | -8.8 ± 1.5 | -9.9% |
| 85% | 5¢ | 3 | through | taker | 767 / 5431 | 76.9% | 86.5% | -9.6 ± 1.5 | -10.8% |
| 85% | 5¢ | 3 | touch | none | 827 / 5431 | 77.6% | 85.7% | -8.1 ± 1.4 | -9.1% |
| 85% | 5¢ | 3 | touch | taker | 827 / 5431 | 77.6% | 86.6% | -9.0 ± 1.4 | -10.0% |
| 85% | 5¢ | 5 | through | none | 1018 / 5431 | 77.4% | 85.7% | -8.3 ± 1.2 | -9.5% |
| 85% | 5¢ | 5 | through | taker | 1018 / 5431 | 77.4% | 86.6% | -9.2 ± 1.2 | -10.3% |
| 85% | 5¢ | 5 | touch | none | 1085 / 5431 | 78.2% | 85.8% | -7.7 ± 1.2 | -8.7% |
| 85% | 5¢ | 5 | touch | taker | 1085 / 5431 | 78.2% | 86.7% | -8.5 ± 1.2 | -9.6% |
| 85% | 5¢ | 10 | through | none | 1340 / 5431 | 77.2% | 86.0% | -8.8 ± 1.1 | -10.0% |
| 85% | 5¢ | 10 | through | taker | 1340 / 5431 | 77.2% | 86.8% | -9.6 ± 1.1 | -10.8% |
| 85% | 5¢ | 10 | touch | none | 1405 / 5431 | 77.9% | 86.1% | -8.1 ± 1.0 | -9.2% |
| 85% | 5¢ | 10 | touch | taker | 1405 / 5431 | 77.9% | 86.9% | -9.0 ± 1.0 | -10.1% |
| 90% | 1¢ | 3 | through | none | 1360 / 5153 | 87.9% | 93.1% | -5.1 ± 0.8 | -5.3% |
| 90% | 1¢ | 3 | through | taker | 1360 / 5153 | 87.9% | 93.5% | -5.6 ± 0.8 | -5.8% |
| 90% | 1¢ | 3 | touch | none | 1580 / 5153 | 89.4% | 93.2% | -3.7 ± 0.7 | -3.9% |
| 90% | 1¢ | 3 | touch | taker | 1580 / 5153 | 89.4% | 93.6% | -4.2 ± 0.7 | -4.3% |
| 90% | 1¢ | 5 | through | none | 1623 / 5153 | 88.2% | 93.1% | -5.0 ± 0.8 | -5.2% |
| 90% | 1¢ | 5 | through | taker | 1623 / 5153 | 88.2% | 93.6% | -5.4 ± 0.8 | -5.6% |
| 90% | 1¢ | 5 | touch | none | 1858 / 5153 | 89.5% | 93.3% | -3.8 ± 0.7 | -3.9% |
| 90% | 1¢ | 5 | touch | taker | 1858 / 5153 | 89.5% | 93.7% | -4.2 ± 0.7 | -4.3% |
| 90% | 1¢ | 10 | through | none | 1874 / 5153 | 88.1% | 93.2% | -5.1 ± 0.7 | -5.3% |
| 90% | 1¢ | 10 | through | taker | 1874 / 5153 | 88.1% | 93.6% | -5.5 ± 0.7 | -5.8% |
| 90% | 1¢ | 10 | touch | none | 2107 / 5153 | 89.4% | 93.3% | -3.9 ± 0.6 | -4.1% |
| 90% | 1¢ | 10 | touch | taker | 2107 / 5153 | 89.4% | 93.7% | -4.4 ± 0.6 | -4.5% |
| 90% | 3¢ | 3 | through | none | 865 / 5153 | 84.9% | 90.8% | -5.9 ± 1.2 | -6.2% |
| 90% | 3¢ | 3 | through | taker | 865 / 5153 | 84.9% | 91.4% | -6.5 ± 1.2 | -6.8% |
| 90% | 3¢ | 3 | touch | none | 969 / 5153 | 86.1% | 90.8% | -4.7 ± 1.1 | -5.0% |
| 90% | 3¢ | 3 | touch | taker | 969 / 5153 | 86.1% | 91.4% | -5.3 ± 1.1 | -5.6% |
| 90% | 3¢ | 5 | through | none | 1113 / 5153 | 84.8% | 90.9% | -6.1 ± 1.0 | -6.4% |
| 90% | 3¢ | 5 | through | taker | 1113 / 5153 | 84.8% | 91.4% | -6.6 ± 1.0 | -7.0% |
| 90% | 3¢ | 5 | touch | none | 1212 / 5153 | 85.9% | 90.9% | -5.0 ± 1.0 | -5.3% |
| 90% | 3¢ | 5 | touch | taker | 1212 / 5153 | 85.9% | 91.5% | -5.6 ± 1.0 | -5.9% |
| 90% | 3¢ | 10 | through | none | 1397 / 5153 | 84.5% | 90.9% | -6.5 ± 0.9 | -6.9% |
| 90% | 3¢ | 10 | through | taker | 1397 / 5153 | 84.5% | 91.5% | -7.0 ± 0.9 | -7.5% |
| 90% | 3¢ | 10 | touch | none | 1494 / 5153 | 85.4% | 91.0% | -5.6 ± 0.9 | -6.0% |
| 90% | 3¢ | 10 | touch | taker | 1494 / 5153 | 85.4% | 91.5% | -6.1 ± 0.9 | -6.5% |
| 90% | 5¢ | 3 | through | none | 624 / 5153 | 81.1% | 88.5% | -7.4 ± 1.5 | -8.0% |
| 90% | 5¢ | 3 | through | taker | 624 / 5153 | 81.1% | 89.2% | -8.1 ± 1.5 | -8.7% |
| 90% | 5¢ | 3 | touch | none | 678 / 5153 | 82.0% | 88.6% | -6.6 ± 1.4 | -7.0% |
| 90% | 5¢ | 3 | touch | taker | 678 / 5153 | 82.0% | 89.3% | -7.3 ± 1.4 | -7.7% |
| 90% | 5¢ | 5 | through | none | 830 / 5153 | 81.7% | 88.6% | -6.9 ± 1.3 | -7.5% |
| 90% | 5¢ | 5 | through | taker | 830 / 5153 | 81.7% | 89.3% | -7.6 ± 1.3 | -8.2% |
| 90% | 5¢ | 5 | touch | none | 894 / 5153 | 82.3% | 88.7% | -6.3 ± 1.2 | -6.9% |
| 90% | 5¢ | 5 | touch | taker | 894 / 5153 | 82.3% | 89.4% | -7.0 ± 1.2 | -7.6% |
| 90% | 5¢ | 10 | through | none | 1105 / 5153 | 81.4% | 88.7% | -7.4 ± 1.1 | -8.1% |
| 90% | 5¢ | 10 | through | taker | 1105 / 5153 | 81.4% | 89.4% | -8.1 ± 1.1 | -8.8% |
| 90% | 5¢ | 10 | touch | none | 1168 / 5153 | 82.2% | 88.8% | -6.6 ± 1.1 | -7.2% |
| 90% | 5¢ | 10 | touch | taker | 1168 / 5153 | 82.2% | 89.5% | -7.3 ± 1.1 | -7.9% |

## Reading it

- A filled order pays its own limit price; the break-even rate is that price plus the fee.
- The fills are a selected set: an order fills only when the market has fallen, which is when the favorite's position has got worse. The win rate is measured on that set.
- One sample a minute of the top of the book: a dip between samples is missed, and a fill assumes no one was ahead of the order at its price. Touch fills are the more generous of the two.
- Elapsed time is not the game clock. The live worker marks late by the venue's period, which this tape does not carry; its paper record is the test of that.
