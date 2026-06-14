# "Spendable Spell" rename stops at the Ramp Tradeoff boundary

We adopted "spendable" terminology (replacing "value") only within the Ramp Tradeoff
code and its new JSON, and deliberately did **not** blanket-rename the shared
`classify_for_curve_value` output keys (`V`, `V_curve`, `V_avg_cmc`). Those keys cross
the result-dict JSON boundary, are consumed by the existing Implied Draw and Implied
Spell Value UI, and persist in cached `simulation_results` rows; "spendable" (can this
absorb mana?) is also the wrong word for Implied Spell Value, which measures the value
a spell *generates*. Renaming the shared contract would couple this feature to three
others and break cached results for no semantic gain.

This reverses an earlier in-session instruction to rename internals everywhere — the
true scope only became clear after grepping the call sites (98 occurrences across 8
files, several crossing the JSON/UI boundary).
