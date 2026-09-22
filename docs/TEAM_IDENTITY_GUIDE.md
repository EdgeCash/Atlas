# Atlas — Team Identity Guide

Rule 3: **a user should identify a game before reading it.**

That is a literal claim about perception, not a style preference. A reader
recognises a familiar mark in roughly 200 milliseconds and reads a team name in
roughly 500. On a board of 58 rows, crests are the difference between scanning
and reading.

---

## The four carriers of identity

In order of how fast they work.

| Carrier | Speed | Where it is used |
|---|---|---|
| **Crest** | instant | Board rows, card hero, driver rows, social templates, team pages |
| **Rank** | fast | Board rows, card hero — where a team has one |
| **Colour** | fast, but weak | An 8px accent rule and nothing else |
| **Name, record, conference** | slow | Card hero, team pages |

**Text is the last resort, not the first.** Where a crest can say it, the crest
says it.

---

## Crests

### Sourcing and serving

142 logos are fetched from the ESPN scoreboard at build time, cached to
`data/site/logos/`, and copied into `site/assets/logos/`. They are **served from
the site, never hot-linked** — a board that waits on a third-party CDN is not a
fast board, and a product that breaks when someone else's cache expires is not a
product.

A team with no logo falls back to a coloured chip in its primary colour. It is a
fallback, never a design element: a coloured square pretending to be a mark is
worse than a mark that is missing.

### Sizes

| Context | Desktop | Phone |
|---|---|---|
| Card hero | 54px | 52px |
| Board row | 30px | 25px |
| Featured cell | 30px | 25px |
| Driver row | 20px | 20px |
| Social wide | 72px | — |
| Social square | 76px | — |

The phone board sits at 25px because at 30px team names begin to wrap, and a
wrapped name costs more than the four pixels gained.

### Rendering

- `object-fit: contain` in a square box, always. Team marks range from wide
  wordmarks (Central Michigan) to narrow letterforms (Miami's U); fitting them
  to a common box keeps optical weight roughly even without cropping anyone.
- Never on a coloured background. Never in a circle — several marks are
  designed to bleed past a circular crop.
- Never recoloured, never given a drop shadow, never at partial opacity.
- Always with an `alt` of the team's short name, so a crest is never the only
  carrier of a team's identity for a screen-reader user.

### The two-crest cluster

Away first, home second, 3px apart, the same order as the title reads. On the
card hero they sit either side of the word "at" — the shape of a matchup, not a
list of two teams.

---

## Colour

**Team colour is chrome. It may never encode a value.**

This is the rule most likely to be broken by accident and the one with the
highest cost. Two cards have to be comparable, and team colours are not a scale:
a bar drawn in Georgia red and a bar drawn in Oklahoma crimson do not mean
anything relative to each other.

### Where team colour is permitted

- The 8px accent rule at the top of a card hero and a social template, split at
  the centre — away on the left, home on the right.
- The fallback chip where a team has no crest.

That is the whole list. Not behind text, not as a chart series, not as a card
background, not as a grade colour.

### The collision rule

When two teams' primary colours are too close to tell apart at chip size — Iowa
State cardinal beside Utah crimson — the away accent falls back to slate.

Implemented as RGB distance with a threshold of 60. A perceptual distance (ΔE in
OKLab) would be better and is not worth the dependency yet. With crests now on
every row the accent carries less of the identity load than it did when the rule
was written, so the fallback costs less than it used to.

### Data colour is not team colour

The data palette is fixed and validated: `#2a78d6` blue, `#e34948` red, `#9aa1aa`
neutral, worst adjacent CVD ΔE 21.6. The market is always drawn in the neutral
because it is a reference, not a competing series. None of these ever changes
with the teams on the card.

---

## Rank

A rank is the strongest "this game matters" signal available that is **not
Atlas's own opinion**, which is exactly why it is worth the space.

- Shown as `#2` in the muted ink, immediately before the team name.
- Both board rows and the card hero.
- Never invented, never extended past 25, never shown for an unranked team.
- Featured selection uses rank as its first key, so the board's top strip is
  chosen by the sport's own consensus rather than by Atlas's numbers.

---

## Records and conference

One line, under the team name in the card hero: `SEC · 3-0`.

- Conference first, because it locates the team; record second, because it
  describes the season.
- Not on board rows. Two more numbers on 58 rows to save one tap is not a
  trade worth making, and the row is already carrying six things.
- The record is the overall record, never a record against the spread — that is
  a betting statistic and `BRAND_GUIDE.md` does not permit publishing one.

---

## Drivers

The driver rows carry **the crest of the team the driver favours**, not a
coloured dot.

Three identical dots read as three of the same thing; three crests say which
team each line is about, which is the actual information. Where a driver favours
neither side — pace, combined plays — the mark is a neutral grey dot, and that
absence is itself meaningful.

Colour alone never carries the meaning here: the crest identifies, and the text
beside it states the direction.

---

## What identity may never do

- **Never imply a side.** A larger crest, a highlighted row, a coloured
  background behind one team, an arrow — all of these read as a lean, and
  `BRAND_GUIDE.md` forbids publishing one.
- **Never replace the grade as the loudest thing on the card.** Team colour is
  an 8px rule; the grade is a 92px mark. If that ever inverts, the card has
  become a poster.
- **Never be the only carrier of information.** Every crest has alt text, every
  colour has a label, every accent is decorative.

---

## Checklist for any new surface

1. Can a reader identify the game without reading a word? If not, the crests are
   too small or absent.
2. Is any colour on this surface carrying a value? If so, it is wrong.
3. Would this surface look different if the two teams swapped colours? If yes,
   something is encoding identity as data.
4. Is the largest element the grade? If not, justify it.
5. Does every crest have alt text and every accent a text equivalent?
