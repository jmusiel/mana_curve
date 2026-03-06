"""Generic candidate cards for deck optimization.

Each candidate is a synthetic card with a known effect (draw or ramp)
that can be injected into a deck during optimization. Cards are generic
(not named MTG cards) so they represent archetypes like "2 mana draw 2".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class CandidateCard:
    """A generic card archetype that can be added to a deck during optimization."""

    id: str
    label: str
    card_type: str  # "draw" or "ramp"
    cmc: int
    default_enabled: bool
    categories: tuple[dict, ...]  # Effect category dicts for registry building

    def to_card_dict(self, index: int = 0) -> Dict[str, Any]:
        """Build a synthetic card dict suitable for Goldfisher._make_card()."""
        return {
            "name": self.registry_name,
            "quantity": 1,
            "oracle_cmc": self.cmc,
            "cmc": self.cmc,
            "cost": f"{{{self.cmc}}}",
            "text": self.label,
            "sub_types": [],
            "super_types": [],
            "types": ["Sorcery"],
            "identity": [],
            "default_category": self.card_type.capitalize(),
            "user_category": f"Optimization {self.card_type.capitalize()}",
            "commander": False,
        }

    @property
    def compact_label(self) -> str:
        """Short label like Draw2(mv2) or Ramp+1(mv2)."""
        cat = self.categories[0] if self.categories else {}
        if self.card_type == "draw":
            if cat.get("immediate"):
                amount = cat.get("amount", 1)
                return f"Draw{amount}(mv{self.cmc})"
            elif cat.get("per_turn"):
                amount = cat["per_turn"].get("amount", 1)
                return f"Draw{amount}/t(mv{self.cmc})"
            else:
                return f"Draw(mv{self.cmc})"
        elif self.card_type == "ramp":
            producer = cat.get("producer", {})
            amount = producer.get("mana_amount", 1)
            return f"Ramp+{amount}(mv{self.cmc})"
        return self.label

    @property
    def registry_name(self) -> str:
        """Unique name used in the effects registry."""
        return f"[Opt] {self.label}"

    def to_registry_override(self) -> Dict[str, Any]:
        """Build an override dict for build_overridden_registry()."""
        override: Dict[str, Any] = {"categories": list(self.categories)}
        if self.card_type == "ramp":
            override["ramp"] = True
        override["priority"] = 1
        return override


# ---------------------------------------------------------------------------
# Default candidate shortlists
# ---------------------------------------------------------------------------

DRAW_CANDIDATES: List[CandidateCard] = [
    CandidateCard(
        id="draw_1cmc_1",
        label="1 Mana Draw 1",
        card_type="draw",
        cmc=1,
        default_enabled=True,
        categories=({"category": "draw", "immediate": True, "amount": 1},),
    ),
    CandidateCard(
        id="draw_2cmc_1",
        label="2 Mana Draw 1",
        card_type="draw",
        cmc=2,
        default_enabled=False,
        categories=({"category": "draw", "immediate": True, "amount": 1},),
    ),
    CandidateCard(
        id="draw_2cmc_2",
        label="2 Mana Draw 2",
        card_type="draw",
        cmc=2,
        default_enabled=True,
        categories=({"category": "draw", "immediate": True, "amount": 2},),
    ),
    CandidateCard(
        id="draw_4cmc_3",
        label="4 Mana Draw 3",
        card_type="draw",
        cmc=4,
        default_enabled=True,
        categories=({"category": "draw", "immediate": True, "amount": 3},),
    ),
    CandidateCard(
        id="draw_3cmc_1pt",
        label="3 Mana Draw 1/turn",
        card_type="draw",
        cmc=3,
        default_enabled=True,
        categories=({"category": "draw", "immediate": False, "per_turn": {"amount": 1}},),
    ),
]

RAMP_CANDIDATES: List[CandidateCard] = [
    CandidateCard(
        id="ramp_2cmc_1",
        label="2 Mana Ramp +1",
        card_type="ramp",
        cmc=2,
        default_enabled=True,
        categories=({"category": "ramp", "immediate": False, "producer": {"mana_amount": 1}},),
    ),
    CandidateCard(
        id="ramp_3cmc_1",
        label="3 Mana Ramp +1",
        card_type="ramp",
        cmc=3,
        default_enabled=False,
        categories=({"category": "ramp", "immediate": False, "producer": {"mana_amount": 1}},),
    ),
    CandidateCard(
        id="ramp_4cmc_2",
        label="4 Mana Ramp +2",
        card_type="ramp",
        cmc=4,
        default_enabled=True,
        categories=({"category": "ramp", "immediate": False, "producer": {"mana_amount": 2}},),
    ),
]

ALL_CANDIDATES: Dict[str, CandidateCard] = {
    c.id: c for c in DRAW_CANDIDATES + RAMP_CANDIDATES
}


def make_custom_candidate(
    card_type: str, cmc: int, amount: int
) -> CandidateCard:
    """Create a user-defined custom candidate at runtime."""
    if card_type == "draw":
        return CandidateCard(
            id=f"draw_custom_{cmc}cmc_{amount}",
            label=f"{cmc} Mana Draw {amount} (Custom)",
            card_type="draw",
            cmc=cmc,
            default_enabled=True,
            categories=({"category": "draw", "immediate": True, "amount": amount},),
        )
    elif card_type == "ramp":
        return CandidateCard(
            id=f"ramp_custom_{cmc}cmc_{amount}",
            label=f"{cmc} Mana Ramp +{amount} (Custom)",
            card_type="ramp",
            cmc=cmc,
            default_enabled=True,
            categories=({"category": "ramp", "immediate": False, "producer": {"mana_amount": amount}},),
        )
    else:
        raise ValueError(f"Unknown card_type: {card_type!r}")
