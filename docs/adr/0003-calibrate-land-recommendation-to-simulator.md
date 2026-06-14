# Calibrate the land-count recommendation to the simulator, anchored to consensus

The hypergeometric Mana Model's `optimal_land_count` recommended a land count by
sweeping land counts and maximizing a hand-weighted composite score (on-curve +
mana + mulligan + flood). That composite had no working flood term, so it climbed
monotonically with land count and recommended the search ceiling for every deck;
a later hand-tuned "dead-land" fix swung the other way and recommended ~8 lands too
few on average (e.g. a 13-ramp cantrip deck → 27 lands). The constants were tuned by
eye against a handful of decks and did not generalize.

We replaced the composite-score sweep with a **closed-form formula fit to the
simulator**: for ~100 real Archidekt decks we ran goldfishing land sweeps (14-turn
horizon, maximizing value-mana spent) to find each deck's empirically-best land
count, then regressed it on deck features.

The key decision is that we **anchor the absolute level to consensus** (a balanced
avg-CMC-3.0 deck → 37 lands) and use the simulator only for the **relative slopes**.
This is deliberate: the goldfishing optimum is noisy (±~3 lands) and strongly
horizon-sensitive — short games reward more lands (flooding never bites), long games
reward fewer (you deplete spells) — so its *absolute* level is not trustworthy, but
the *direction and magnitude* of how the optimum shifts with curve/ramp/draw is.

Resulting formula (see `mana_model.py`, `scripts/fit_land_model.py`):

    recommended = clamp( 37 + 1.2·(avgCMC − 3.0) − 0.10·ramp − 0.05·draw , 30, 43 )

Average mana value is the dominant, robust driver (+~1.2 lands/CMC, sim-derived).
Ramp gets a small reduction (sim-derived). Draw gets a small *conventional* reduction:
the simulator's draw signal was unreliable (draw-heavy decks censored at the sweep
floor produced a spurious positive slope), so we used a conventional value instead.

## Consequences

- Recommendations are consensus-centered and curve-sensitive (mean ~36 vs the old
  model's ~28); hermes goes 27 → 34, matching its simulator optimum.
- The composite-score machinery (`_score_land_count`, the on-curve/mana/mulligan/
  dead-land weights, `useful_lands`) and its magic numbers were removed. The
  `scores` curve is now a simple closeness-to-recommendation curve for display.
- The recommendation no longer uses commander CMC directly (only deck avg CMC), so
  a high-CMC partner pair no longer strictly raises the count.
- Recalibrate with `scripts/fit_land_model.py` if the engine or meta changes.
