---
status: accepted
---

# Ramp Tradeoff compute model: eager-in-view, lazy-cached, single reused draw signature

Ramp Tradeoff is computed eagerly for the land count currently in view (as part of
`result_to_dict`) and lazily — compute-on-demand, then cached — for the other land
counts in a land sweep. Every variant reuses the main simulation's measured draw
signature (`mean_cumulative_draws_per_turn`) instead of running a second warm-up
simulation. We chose this after measuring that the panel cost is fixed at roughly
160 ms native (~0.6 s in Pyodide) for 8 variants × 1000 trials and is *independent*
of the main sim count, so computing it eagerly for every land count would roughly
double wall-clock on a default-settings land sweep in the browser.

## Considered Options

- **Eager compute for every land count.** Rejected: a 5-land sweep at default sims
  adds ~2.5–4 s of panel work in-browser on every run, a perceptible freeze for
  panels the user may never scroll to.
- **Lazy/on-click for all panels.** Rejected: the panel should be present for the
  result in view without an extra action (Q1 — diagnostic-first, immediately useful).
- **Divide the trial budget by the number of land counts** to keep the total flat.
  Rejected: fewer trials widen the Monte Carlo noise band and starve the
  noise-gated tuning callouts.

## Consequences

- **The draw signature is held invariant across variants.** A single signature,
  measured at the deck's *current* ramp, is applied to every rock-equivalent
  variant. This holds card flow fixed while only ramp varies, which **flattens the
  tradeoff curve relative to reality**: it understates how much cutting ramp hurts
  card flow (fewer cantrips resolve with less mana) and how much adding ramp speeds
  card deployment. The bias is most pronounced on cantrip-engine decks and skews
  toward making "cut ramp" look safe. It is inherent to the deliberately cheap,
  non-simulated draw model — a second warm-up sim would not fix it.
- **Panel math must be a pure function of the serialized result dict** (draw
  signature + classification + commanders). It may not depend on live simulator
  state, which is what lets the lazy path recompute a panel without re-simulating.
- **Signature precision is tied to the run's sim count.** A low-sim run yields a
  noisy signature whose bias propagates identically across all variants and is not
  averaged out by the panel's own trials — so the panel should not be over-trusted
  on small sim counts.
