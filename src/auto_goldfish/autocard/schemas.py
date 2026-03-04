"""Data schemas for Scryfall card data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScryfallCard:
    """Minimal representation of a Scryfall card for autocard labeling."""

    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: List[str]
    color_identity: List[str]
    keywords: List[str]
    edhrec_rank: Optional[int] = None
    layout: str = "normal"
    card_faces: Optional[List[Dict[str, Any]]] = None
    produced_mana: List[str] = field(default_factory=list)
    otags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "mana_cost": self.mana_cost,
            "cmc": self.cmc,
            "type_line": self.type_line,
            "oracle_text": self.oracle_text,
            "colors": self.colors,
            "color_identity": self.color_identity,
            "keywords": self.keywords,
            "edhrec_rank": self.edhrec_rank,
            "layout": self.layout,
            "card_faces": self.card_faces,
            "produced_mana": self.produced_mana,
            "otags": self.otags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScryfallCard:
        """Deserialize from a dictionary."""
        return cls(
            name=data["name"],
            mana_cost=data["mana_cost"],
            cmc=data["cmc"],
            type_line=data["type_line"],
            oracle_text=data["oracle_text"],
            colors=data["colors"],
            color_identity=data["color_identity"],
            keywords=data["keywords"],
            edhrec_rank=data.get("edhrec_rank"),
            layout=data.get("layout", "normal"),
            card_faces=data.get("card_faces"),
            produced_mana=data.get("produced_mana", []),
            otags=data.get("otags", []),
        )

    @classmethod
    def from_scryfall_object(cls, card: Any) -> ScryfallCard:
        """Build a ScryfallCard from a scrython card object.

        Handles double-faced cards by concatenating oracle text from faces
        with '//' separator (same pattern as archidekt.py).

        Scrython card objects expose fields as properties (not methods).
        """
        oracle_text = ""
        mana_cost = ""
        card_faces_data = None

        # Double-faced / modal cards store data in card_faces
        faces = card.card_faces
        if faces:
            card_faces_data = faces
            text_parts = []
            cost_parts = []
            for face in faces:
                text_parts.append(face.get("oracle_text", ""))
                cost_parts.append(face.get("mana_cost", ""))
            oracle_text = " // ".join(text_parts)
            mana_cost = " // ".join(cost_parts)
        else:
            oracle_text = card.oracle_text or ""
            mana_cost = card.mana_cost or ""

        try:
            produced = card.produced_mana
        except (AttributeError, KeyError):
            produced = []

        return cls(
            name=card.name,
            mana_cost=mana_cost,
            cmc=card.cmc,
            type_line=card.type_line,
            oracle_text=oracle_text,
            colors=card.colors,
            color_identity=card.color_identity,
            keywords=card.keywords,
            edhrec_rank=card.edhrec_rank,
            layout=card.layout,
            card_faces=card_faces_data,
            produced_mana=produced or [],
        )
