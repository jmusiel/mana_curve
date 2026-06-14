# Auto Goldfish

A goldfishing simulator and mana-base optimizer for Magic: The Gathering Commander
decks. It serves two audiences at once: the author and optimization-curious friends
(who want the sophisticated machinery to stay **legible**), and intermediate
Commander players who know MTG but not Monte Carlo / optimization theory (who want a
plain answer to *"is my mana base right, and what should I change?"*). The design
layers a plain-language path on top of the power-user tooling without hiding the
latter.

## Language

**Goldfishing**:
Simulating games of a deck with no opponent, to measure how reliably it develops mana
and casts spells.

**Mana base**:
The lands + ramp + draw that determine whether a deck reliably has mana to spend.
The core question the app answers is whether a deck's mana base is right.

**Mana Model**:
The instant, closed-form (hypergeometric) land-count recommender. Answers the *lands*
half of the mana-base question with no simulation.
_Avoid_: "calculator" (it is a recommender, not just arithmetic).

**Simulator**:
The goldfishing + optimization engine that runs many simulated games to validate land
count, optimize ramp/draw additions, and produce the CASTER score. The deeper, slower
counterpart to the Mana Model.

**Deck Home**:
The per-deck landing page that is the spine of the new-user journey. Leads with a
prominent **Run a simulation** call-to-action (the primary thing to do here) plus a
compact, instant Mana Model land readout. The CASTER score is *not* shown here — it
requires a run and appears in the results afterwards.

**CASTER score**:
A 1-10 stat block (Consistency, Acceleration, Snowball, Tuning, Efficiency, Reach)
derived from simulation metrics, calibrated against other runs. The intended hook for
intermediate players — a shareable, intuitive summary of deck quality. Headlined by a
single **overall** number (plain mean of the six axes) for at-a-glance hook/sharing,
but the six-stat radar remains the centerpiece — the overall never replaces the profile.
_Avoid_: listing the old sixth stat "Toughness" (replaced by "Tuning").

**Ramp**:
A spell/effect that adds mana (producers, cost reducers, lands-to-battlefield).

**Draw**:
A spell/effect that draws cards (immediate, per-turn, or per-cast).

**Value spell**:
A non-land, non-ramp, non-draw spell — the spells whose casting "mana spent" measures.

**Ramp Tradeoff**:
A diagnostic view of how changing a deck's ramp count shifts early-ramp likelihood,
expected unspent mana, and expected stuck cards.
_Avoid_: Ramp Recommendation, correct Signet count, scenario analysis.

**Signet-Equivalent Variant**:
A counterfactual deck variant that changes ramp by generic Arcane Signet-style equivalents
while conserving deck slots against the value curve.
_Avoid_: Candidate edit, specific card swap.

**Spendable Spell**:
A non-ramp spell in the library that can absorb mana in ramp diagnostics, including draw
spells.
_Avoid_: Value spell, non-draw value spell, filler.

**Spend Rate**:
The fraction of available mana a variant actually spends (`mana spent / mana available`);
shown per variant, not as a score to maximise.
_Avoid_: Efficiency, mana utilisation score.

**Early Ramp**:
The Signet-equivalent ramp pieces a deck has seen by the end of turn 5, bucketed
as 0 / 1 / 2 / 3+; the basis of the scenario-frequency bars.
_Avoid_: Fast ramp, turn-1 ramp.

## Relationships

- A user imports a deck, then lands on its **Deck Home**.
- **Deck Home** leads with a prominent **Simulator** call-to-action and a compact instant
  **Mana Model** land readout; running the **Simulator** validates lands, optimizes
  **Ramp**/**Draw**, and produces the **CASTER score** (shown in the results, shareable).
- The **Mana Model** answers a subset of what the **Simulator** answers, but instantly
  and without simulation.
- The **CASTER score** is produced only by a **Simulator** run, not by the Mana Model.
- A **Ramp Tradeoff** compares multiple ramp-count variants of the same deck.
- A **Signet-Equivalent Variant** is an abstract diagnostic input to a **Ramp Tradeoff**,
  not a concrete deck edit.
- A **Signet-Equivalent Variant** conserves slots by trading ramp against
  **Spendable Spells**.
- A **Ramp Tradeoff** is diagnostic first and may provide tuning guidance, but it does
  not prescribe one correct Signet count.
- Each **Signet-Equivalent Variant** reports a **Spend Rate** alongside its expected
  unspent mana and stuck cards.
- A **Ramp Tradeoff** reports **Early Ramp** scenario frequencies per variant.

## Example dialogue

> **Newcomer:** "Is my mana base right?"
> **App (Deck Home):** "Your 34 lands look ~2 low — about 36 is the sweet spot (instant
> Mana Model). Run a simulation to optimize ramp/draw and get your CASTER score."

> **Dev:** "Should the **Ramp Tradeoff** tell the user exactly how many Signets to run?"
> **Domain expert:** "No — show how each ramp count changes the deck's outcomes, then provide cautious tuning guidance."
> **Dev:** "Does '+1 Signet' mean adding Arcane Signet?"
> **Domain expert:** "No — it means one generic Signet-equivalent two-mana ramp slot, not a specific card edit."
> **Dev:** "Do cantrips count as **Spendable Spells** here?"
> **Domain expert:** "Yes — for ramp diagnostics, a draw spell still absorbs mana and should count."

## Flagged ambiguities

- "Mana Model" vs "Simulator" were undifferentiated sibling buttons; resolved as a
  funnel — instant math answer first, deep simulated optimization second.
- The CASTER sixth stat was renamed Toughness → **Tuning**; the README still says
  Toughness in places.
- "scenario analysis" was used for this feature, but the resolved term is
  **Ramp Tradeoff** because the feature specifically diagnoses ramp-count variants.
- "+1 Signet" could imply a concrete card edit, but it is resolved as a
  **Signet-Equivalent Variant**.
- "value spell" is legacy wording for **Spendable Spell** and should be replaced in
  Ramp Tradeoff code and user-facing UI only. The shared classifier keeps "value"
  terminology because it also feeds Implied Spell Value, where "value" means the worth
  a spell *generates*, not the mana it *absorbs* — a distinct concept that
  **Spendable Spell** does not cover. The rename stops at the Ramp Tradeoff boundary.
