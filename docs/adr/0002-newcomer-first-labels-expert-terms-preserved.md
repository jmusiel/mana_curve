# Newcomer-first labels with expert terms preserved as subtitles

The UI is full of precise expert terms (Karsten-ECMS, Factored, Hyperband, Racing,
the CASTER axes, "value/value+draw/total" mana modes). These terms *are* the legibility
the project values for power users, but they are exactly what an intermediate player
cannot parse. Renaming them to softer words would destroy that legibility and lose the
correct term.

We decided that on **default surfaces**, the plain-language phrasing is the *primary*
visible label and the precise expert term is demoted to a subtitle or tooltip — e.g.
**"Best all-around"** as the title with **"Karsten-ECMS"** as a small subtitle. The two
are always paired; neither is ever removed. Inside Advanced / power-user sections the
ordering flips to expert-first. We chose newcomer-first over expert-first for the big
text because the new audience reads the default surfaces, while power users still get the
exact term every time it appears.

## Consequences

- Every bare expert term on a default surface must carry a plain-language gloss
  (label subtitle or `info-tip` tooltip). No un-glossed jargon on default surfaces.
- Labels read like "Best all-around (Karsten-ECMS)"; a future reader should not
  "simplify" these back down to a single term — the pairing is deliberate.
