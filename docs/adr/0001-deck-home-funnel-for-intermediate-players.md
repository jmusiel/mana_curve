# Expand to intermediate players via a layered Deck Home funnel

Auto Goldfish began as a personal optimizer where the priority was making
sophisticated machinery (factored Monte Carlo, CRN-paired marginal analysis,
hypergeometric mana modelling) **legible** to the author and optimization-curious
friends. We are expanding the audience to include intermediate Commander players who
know MTG but not optimization theory, whose single job is *"is my deck's mana base
(lands + ramp + draw) right, and what should I change?"*

We resolved the legibility-vs-approachability tension as **both, layered**: rather than
hide or dumb down the machinery, we add a plain-language path on top of it. The spine of
that path is a per-deck **Deck Home** page (built on the former `deck_view.html`) that a
user lands on after import and that funnels them: instant **Mana Model** land verdict →
**Simulator** run → **CASTER** score. The two analysis tools, previously undifferentiated
sibling buttons, are now an explicit funnel (instant closed-form answer first, deep
simulated optimization second). All power-user tooling stays fully reachable and
unmodified in capability — only the entry path and framing change.

## Consequences

- Import now lands on Deck Home, not the Simulate form (the heaviest surface is no
  longer a newcomer's first touch).
- The Simulate page becomes a downstream "go deeper" surface rather than the entry point.
- CASTER is promoted to a headline result (see ADR-0002 sibling work) because it is the
  intended hook for the new audience.
