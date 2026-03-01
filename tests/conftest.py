"""Shared test fixtures for the mana_curve test suite."""

import pytest

from mana_curve.models.card import Card
from mana_curve.models.game_state import GameState


# ---------------------------------------------------------------------------
# Card fixtures
# ---------------------------------------------------------------------------

def make_card(name: str = "Test Card", cmc: int = 2, types: list | None = None, **kw) -> Card:
    """Quick helper to build a Card with sensible defaults."""
    return Card(
        name=name,
        cmc=cmc,
        oracle_cmc=kw.pop("oracle_cmc", cmc),
        cost=kw.pop("cost", f"{{{cmc}}}"),
        text=kw.pop("text", ""),
        types=types or ["creature"],
        **kw,
    )


@pytest.fixture
def sol_ring() -> Card:
    return make_card("Sol Ring", cmc=1, types=["artifact"], cost="{1}")


@pytest.fixture
def basic_island() -> Card:
    return make_card(
        "Island",
        cmc=0,
        types=["land"],
        cost="",
        text="({T}: Add {U}.)",
        sub_types=["Island"],
        super_types=["Basic"],
    )


@pytest.fixture
def grizzly_bears() -> Card:
    return make_card("Grizzly Bears", cmc=2, types=["creature"], cost="{1}{G}")


@pytest.fixture
def lightning_bolt() -> Card:
    return make_card("Lightning Bolt", cmc=1, types=["instant"], cost="{R}")


# ---------------------------------------------------------------------------
# GameState fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_game_state() -> GameState:
    """A fresh GameState with no cards."""
    return GameState()
