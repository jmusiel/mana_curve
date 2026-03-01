"""Core goldfishing simulation engine.

Refactored to use the effects system, GameState, and Card dataclass.
No CLI code here -- returns structured ``SimulationResult``.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from tqdm import tqdm

from mana_curve.effects.card_database import DEFAULT_REGISTRY
from mana_curve.effects.registry import CardEffects, EffectRegistry
from mana_curve.effects.types import CastTriggerEffect, ManaFunctionEffect, OnPlayEffect, PerTurnEffect
from mana_curve.engine.mana import land_mana, mana_rocks
from mana_curve.engine.mulligan import DefaultMulligan, MulliganStrategy
from mana_curve.models.card import Card
from mana_curve.models.game_state import GameState


# ---------------------------------------------------------------------------
# SimulationResult
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Structured return from ``Goldfisher.simulate()``.

    Replaces the old 15-element tuple.
    """

    land_count: int = 0
    mean_mana: float = 0.0
    consistency: float = 0.0
    mean_bad_turns: float = 0.0
    mean_mid_turns: float = 0.0
    mean_lands: float = 0.0
    mean_mulls: float = 0.0
    mean_draws: float = 0.0
    percentile_25: float = 0.0
    percentile_50: float = 0.0
    percentile_75: float = 0.0
    threshold_percent: float = 0.0
    threshold_mana: float = 0.0
    con_threshold: float = 0.25
    distribution_stats: Dict[str, float] = field(default_factory=dict)
    game_records: Dict[str, Dict[str, list]] = field(default_factory=dict)

    def as_row(self) -> list:
        """Return a flat list for tabulate (without distribution_stats)."""
        return [
            self.land_count,
            self.mean_mana,
            self.consistency,
            self.mean_bad_turns,
            self.mean_mid_turns,
            self.mean_lands,
            self.mean_mulls,
            self.mean_draws,
            self.percentile_25,
            self.percentile_50,
            self.percentile_75,
            self.threshold_percent,
            self.threshold_mana,
        ]


# ---------------------------------------------------------------------------
# Module-level helpers (used by effects via import)
# ---------------------------------------------------------------------------

# Reference to the decklist -- set by the engine before each game
_active_decklist: List[Card] = []
_active_deckdict: Dict[str, Card] = {}


def _draw(state: GameState) -> None:
    """Draw a card from the deck into the hand."""
    if not state.deck:
        state.log.append("Draw failed, deck is empty")
        state.draws += 1
        return
    drawn_i = state.deck.pop()
    drawn = _active_decklist[drawn_i]
    drawn.zone = state.hand
    state.hand.append(drawn_i)
    state.draws += 1
    state.log.append(f"Draw {drawn.printable}")


def _random_discard(state: GameState) -> None:
    """Discard a random card from hand."""
    discarded_i = random.choice(state.hand)
    discarded = _active_decklist[discarded_i]
    discarded.change_zone(state.yard)
    state.log.append(f"Discarded {discarded.printable}")


def _find_card_by_name(state: GameState, name: str) -> Card | None:
    """Find a card in the decklist by name."""
    return _active_deckdict.get(name)


# ---------------------------------------------------------------------------
# Goldfisher engine
# ---------------------------------------------------------------------------

class Goldfisher:
    """Core simulation engine.

    Parameters
    ----------
    decklist_dicts : list[dict]
        Raw card dicts (from JSON or Archidekt).
    turns : int
        Number of turns to simulate per game.
    sims : int
        Number of games to simulate.
    verbose : bool
        Print game logs.
    registry : EffectRegistry, optional
        Card effects registry. Uses DEFAULT_REGISTRY if not provided.
    mulligan_strategy : MulliganStrategy, optional
        Mulligan strategy. Uses DefaultMulligan if not provided.
    """

    def __init__(
        self,
        decklist_dicts: list[dict],
        turns: int,
        sims: int,
        verbose: bool = False,
        registry: EffectRegistry | None = None,
        mulligan_strategy: MulliganStrategy | None = None,
        record_results: str = "quartile",
        deck_name: str | None = None,
        seed: int | None = None,
        **kwargs,
    ):
        self.registry = registry or DEFAULT_REGISTRY
        self.mulligan_strategy = mulligan_strategy or DefaultMulligan()
        self.turns = turns
        self.sims = sims
        self.verbose = verbose
        self.seed = seed

        # Separate commanders from the decklist
        self.commanders: list[Card] = []
        non_commander_dicts: list[dict] = []
        commander_index = 0
        for card_dict in decklist_dicts:
            if card_dict.get("commander", False):
                card = self._make_card(card_dict, commander_index)
                self.commanders.append(card)
                commander_index += 1
            else:
                non_commander_dicts.append(card_dict)

        # Build decklist
        self.decklist: list[Card] = [
            self._make_card(d, i) for i, d in enumerate(non_commander_dicts)
        ]
        self.deckdict: dict[str, Card] = {c.name: c for c in self.decklist}

        self.deck_name = deck_name or "_-_".join(
            c.name for c in self.commanders
        ).replace(" ", "_").replace(",", "")

        self.land_count = sum(1 for c in self.decklist if c.land)
        self.original_card_count = len(self.decklist)

        # Recording config
        self.record_quartile = False
        self.record_decile = False
        self.record_centile = False
        self.record_half = True
        if record_results == "quartile":
            self.record_quartile = self.record_decile = self.record_centile = True
        elif record_results == "decile":
            self.record_decile = self.record_centile = True
        elif record_results == "centile":
            self.record_centile = True

    def _make_card(self, card_dict: dict, index: int) -> Card:
        """Create a Card from a raw dict, applying registry effects."""
        # Clean up dict for Card dataclass
        kw = {
            "name": card_dict.get("name", ""),
            "quantity": card_dict.get("quantity", 1),
            "oracle_cmc": card_dict.get("oracle_cmc", 0),
            "cmc": card_dict.get("cmc", 0),
            "cost": card_dict.get("cost", ""),
            "text": card_dict.get("text", ""),
            "sub_types": card_dict.get("sub_types", []),
            "super_types": card_dict.get("super_types", []),
            "types": list(card_dict.get("types", [])),
            "identity": card_dict.get("identity", []),
            "default_category": card_dict.get("default_category"),
            "user_category": card_dict.get("user_category"),
            "tag": card_dict.get("tag"),
            "commander": card_dict.get("commander", False),
            "index": index,
        }

        # Apply registry overrides
        effects = self.registry.get(kw["name"])
        if effects:
            if effects.extra_types:
                for t in effects.extra_types:
                    if t not in kw["types"]:
                        kw["types"].append(t)
            if effects.override_cmc is not None:
                kw["cmc"] = effects.override_cmc

        card = Card(**kw)

        # Apply card-level flags from registry
        if effects:
            card.ramp = effects.ramp
            card.priority = effects.priority
            card.tapped = effects.tapped

        # Default: if it's a land, mark as not tapped unless registry says otherwise
        if card.land and not card.spell and not effects:
            card.tapped = False

        return card

    def _reset(self) -> GameState:
        """Create a fresh GameState for a new game."""
        state = GameState()
        state.card_cast_turn = [None] * len(self.decklist)

        # Set up module-level references for effects
        global _active_decklist, _active_deckdict
        _active_decklist = self.decklist
        _active_deckdict = self.deckdict

        # Place commanders in command zone
        for card in self.commanders:
            card.zone = state.command_zone
            state.command_zone.append(card.index)

        # Place all cards in deck
        for card in self.decklist:
            card.zone = state.deck
            state.deck.append(card.index)

        random.shuffle(state.deck)

        # Default mana functions
        state.mana_functions = [land_mana, mana_rocks]

        return state

    def _mulligan(self, state: GameState) -> int:
        """Execute mulligan logic. Returns the number of mulligans taken."""
        mulligans = -1
        while True:
            # Reset state for this mulligan attempt
            state.log = []
            state.turn = 0
            state.draws = 0
            state.command_zone = []
            state.deck = []
            state.yard = []
            state.hand = []
            state.battlefield = []
            state.exile = []
            state.lands = []
            state.mana_production = 0
            state.treasure = 0
            state.per_turn_effects = []
            state.cast_triggers = []
            state.mana_functions = [land_mana, mana_rocks]
            state.lands_per_turn = 1
            state.nonpermanent_cost_reduction = 0
            state.permanent_cost_reduction = 0
            state.spell_cost_reduction = 0
            state.creature_cost_reduction = 0
            state.enchantment_cost_reduction = 0
            state.creatures_played = 0
            state.enchantments_played = 0
            state.artifacts_played = 0
            state.card_cast_turn = [None] * len(self.decklist)

            for card in self.commanders:
                card.zone = state.command_zone
                state.command_zone.append(card.index)
            for card in self.decklist:
                card.zone = state.deck
                state.deck.append(card.index)
            random.shuffle(state.deck)

            if mulligans == -1:
                state.log.append("### Opening hand:")
            else:
                state.log.append(f"### Mulligan #{mulligans + 1}")

            cards = 7
            if mulligans > 0:
                cards -= mulligans
            mulligans += 1

            lands_in_hand = 0
            for _ in range(cards):
                _draw(state)
            for i in state.hand:
                if self.decklist[i].land:
                    lands_in_hand += 1

            if self.mulligan_strategy.should_keep(state, len(state.hand), lands_in_hand):
                break

        state.starting_hand = [self.decklist[i] for i in state.hand]
        state.starting_hand_land_count = lands_in_hand
        state.log.append(f"### Kept {lands_in_hand}/{len(state.hand)} lands/cards")
        return mulligans

    def _get_mana(self, state: GameState) -> int:
        """Calculate total available mana."""
        mana = 0
        for func in state.mana_functions:
            if callable(func):
                mana += func(state)
            elif isinstance(func, ManaFunctionEffect):
                mana += func.mana_function(state)
        return mana

    def _get_playables(self, state: GameState, available_mana: int) -> list[Card]:
        """Find all castable spells in hand and command zone."""
        playables = []
        for i in state.hand:
            card = self.decklist[i]
            if card.get_current_cost(state) <= available_mana and card.spell:
                playables.append(card)
                if state.card_cast_turn[i] is None:
                    state.card_cast_turn[i] = state.turn + 1

        for i in state.command_zone:
            card = self.commanders[i]
            if card.get_current_cost(state) <= available_mana and card.spell:
                playables.append(card)

        playables = sorted(playables)

        playables_str = []
        for card in playables:
            if card.commander:
                playables_str.append(f"{card.cmc}(c)")
            else:
                playables_str.append(f"{card.cmc}")
        state.log.append(f"--Playable Spells: {playables_str}")

        return playables

    def _play_land(self, state: GameState) -> list[Card]:
        """Play lands from hand."""
        played = []
        playable_lands = sorted(
            [self.decklist[i] for i in state.hand if self.decklist[i].land]
        )
        for land in reversed(playable_lands):
            if state.played_land_this_turn < state.lands_per_turn:
                land.change_zone(state.lands)
                state.log.append(f"Played as land {land.printable}")
                land.mana_spent_when_played = 0
                played.append(land)
                state.played_land_this_turn += 1
                if not land.tapped:
                    state.untapped_land_this_turn += 1

                # Apply on_play effects for lands
                effects = self.registry.get(land.name)
                if effects:
                    for eff in effects.on_play:
                        if isinstance(eff, OnPlayEffect):
                            eff.on_play(land, state)
                    for eff in effects.mana_function:
                        state.mana_functions.append(eff)
            else:
                break
        return played

    def _play_spells(self, state: GameState) -> list[Card]:
        """Play spells from hand using greedy approach."""
        mana_available = self._get_mana(state) + state.treasure
        played_effects: list[Card] = []

        played_effects.extend(self._play_land(state))
        mana_available += state.untapped_land_this_turn
        state.untapped_land_this_turn = 0

        playables = self._get_playables(state, mana_available)
        while playables:
            for card in reversed(playables):
                cost = card.get_current_cost(state)
                if cost <= mana_available:
                    mana_available -= cost
                    if card.spell and card.nonpermanent:
                        card.change_zone(state.yard)
                    elif card.spell and card.permanent:
                        card.change_zone(state.battlefield)

                    # Apply cast triggers from cards already in play
                    for trigger_data in state.cast_triggers:
                        trigger_card, trigger_eff = trigger_data
                        trigger_eff.cast_trigger(trigger_card, card, state)

                    # Register this card's effects
                    effects = self.registry.get(card.name)
                    if effects:
                        for eff in effects.cast_trigger:
                            state.cast_triggers.append((card, eff))
                        for eff in effects.per_turn:
                            state.per_turn_effects.append((card, eff))
                        for eff in effects.mana_function:
                            state.mana_functions.append(eff)

                    # Execute on_play effects
                    state.log.append(f"Played {card.printable}")
                    card.mana_spent_when_played = card.cmc
                    if card.creature:
                        state.creatures_played += 1
                    if card.enchantment:
                        state.enchantments_played += 1
                    if card.artifact:
                        state.artifacts_played += 1

                    if effects:
                        for eff in effects.on_play:
                            if isinstance(eff, OnPlayEffect):
                                eff.on_play(card, state)

                    played_effects.append(card)

            played_effects.extend(self._play_land(state))
            mana_available += state.untapped_land_this_turn
            state.untapped_land_this_turn = 0
            playables = self._get_playables(state, mana_available)

        if mana_available < state.treasure:
            state.log.append(f"Spent treasures: [{state.treasure}] -> [{mana_available}]")
            state.treasure = mana_available

        return played_effects

    def _take_turn(self, state: GameState) -> list[Card]:
        """Execute one turn."""
        state.log.append(
            f"### Turn {state.turn + 1} "
            f"(Lands: {len(state.lands)}, Mana: {self._get_mana(state)}[{state.treasure}], "
            f"Hand: {len(state.hand)})"
        )
        state.played_land_this_turn = 0
        state.untapped_land_this_turn = 0
        state.tapped_creatures_this_turn = 0
        _draw(state)

        # Per-turn effects
        for card, eff in state.per_turn_effects:
            eff.per_turn(card, state)

        return self._play_spells(state)

    def set_lands(self, land_count: int, cuts: list[str] | None = None) -> None:
        """Adjust the deck's land count."""
        from mana_curve.decklist.loader import get_basic_island

        cuts = cuts or []
        cutted = []
        spells_list = []
        lands_list = []

        for card in self.decklist:
            if card.land:
                lands_list.append(card)
            else:
                spells_list.append(card)

        land_diff = land_count - len(lands_list)
        while land_diff > 0:
            lands_list.append(self._make_card(get_basic_island(), len(spells_list) + len(lands_list)))
            land_diff -= 1
            if cuts and len(spells_list) + len(lands_list) > self.original_card_count:
                for card in spells_list:
                    if card.name in cuts:
                        spells_list.remove(card)
                        cutted.append(card.name)
                        break

        while land_diff < 0:
            for card in lands_list:
                if not card.spell:
                    lands_list.remove(card)
                    cutted.append(card.name)
                    break
            land_diff += 1

        updated = spells_list + lands_list
        self.decklist = [
            self._make_card(
                {
                    "name": c.name, "quantity": c.quantity, "oracle_cmc": c.oracle_cmc,
                    "cmc": c.cmc, "cost": c.cost, "text": c.text,
                    "sub_types": c.sub_types, "super_types": c.super_types,
                    "types": c.types, "identity": c.identity,
                    "default_category": c.default_category, "user_category": c.user_category,
                    "tag": c.tag, "commander": c.commander,
                },
                i,
            )
            for i, c in enumerate(updated)
        ]
        self.deckdict = {c.name: c for c in self.decklist}

        if cutted:
            print(f"Cutted: {cutted}")
        print(
            f"\nSet land count to {land_count} prev {self.land_count} "
            f"({len(lands_list)} lands, {len(spells_list)} spells, total {len(self.decklist)})"
        )
        self.land_count = sum(1 for c in self.decklist if c.land)

    def simulate(self) -> SimulationResult:
        """Run all simulations and return a ``SimulationResult``."""
        sample_games = max(self.sims / 10, 100)
        top_centile_threshold = None
        game_records: dict[str, dict[str, list]] = {
            k: defaultdict(list)
            for k in [
                "top_centile", "low_centile",
                "top_decile", "low_decile",
                "top_quartile", "low_quartile",
                "top_half", "low_half",
            ]
        }

        mana_spent_list = []
        mulls_list = []
        lands_played_list = []
        cards_drawn_list = []
        bad_turns_list = []
        mid_turns_list = []
        card_cast_turn_list: list[list] = [[] for _ in self.decklist]

        for j in tqdm(range(self.sims), leave=False):
            if self.seed is not None:
                random.seed(self.seed + j)
            state = self._reset()
            mulligans = self._mulligan(state)

            total_mana_spent = 0
            lands_played = 0
            bad_turns = 0
            mid_turns = 0
            all_cards_played: list[Card] = []

            for i in range(self.turns):
                mana_spent = 0
                spells_played = 0
                played = self._take_turn(state)

                for card in played:
                    all_cards_played.append(card)
                    if not card.ramp:
                        mana_spent += card.mana_spent_when_played
                    if card.land:
                        lands_played += 1
                    if card.spell:
                        spells_played += 1

                if spells_played == 0 and state.deck:
                    bad_turns += 1
                if spells_played < 2 and state.deck and mana_spent < i + 1:
                    mid_turns += 1
                total_mana_spent += mana_spent

            mana_spent_list.append(total_mana_spent)
            lands_played_list.append(lands_played)
            mulls_list.append(mulligans)
            cards_drawn_list.append(state.draws)
            bad_turns_list.append(bad_turns)
            mid_turns_list.append(mid_turns)

            for k, turn in enumerate(state.card_cast_turn):
                if turn is not None and not self.decklist[k].land:
                    card_cast_turn_list[k].append(turn)

            # Record games in buckets
            if j > sample_games:
                if top_centile_threshold is None:
                    top_centile_threshold = np.percentile(mana_spent_list, 99)
                    low_centile_threshold = np.percentile(mana_spent_list, 1)
                    top_decile_threshold = np.percentile(mana_spent_list, 90)
                    low_decile_threshold = np.percentile(mana_spent_list, 10)
                    top_quartile_threshold = np.percentile(mana_spent_list, 75)
                    low_quartile_threshold = np.percentile(mana_spent_list, 25)
                    median_threshold = np.percentile(mana_spent_list, 50)
                else:
                    record_games = []
                    if self.record_centile and total_mana_spent >= top_centile_threshold:
                        record_games.extend(["top_centile", "top_decile", "top_quartile", "top_half"])
                    elif self.record_decile and total_mana_spent >= top_decile_threshold:
                        record_games.extend(["top_decile", "top_quartile", "top_half"])
                    elif self.record_quartile and total_mana_spent >= top_quartile_threshold:
                        record_games.extend(["top_quartile", "top_half"])
                    elif self.record_half and total_mana_spent >= median_threshold:
                        record_games.append("top_half")

                    if self.record_centile and total_mana_spent <= low_centile_threshold:
                        record_games.extend(["low_centile", "low_decile", "low_quartile", "low_half"])
                    elif self.record_decile and total_mana_spent <= low_decile_threshold:
                        record_games.extend(["low_decile", "low_quartile", "low_half"])
                    elif self.record_quartile and total_mana_spent <= low_quartile_threshold:
                        record_games.extend(["low_quartile", "low_half"])
                    elif self.record_half and total_mana_spent < median_threshold:
                        record_games.append("low_half")

                    for rg in record_games:
                        if len(game_records[rg]["logs"]) < 10:
                            game_records[rg]["logs"].append(state.log)
                        game_records[rg]["mana"].append(total_mana_spent)
                        game_records[rg]["lands"].append(lands_played)
                        game_records[rg]["mulls"].append(mulligans)
                        game_records[rg]["draws"].append(state.draws)
                        game_records[rg]["bad_turns"].append(bad_turns)
                        game_records[rg]["mid_turns"].append(mid_turns)
                        game_records[rg]["surplus mana production"].append(
                            self._get_mana(state) - lands_played
                        )
                        game_records[rg]["nonpermanent cost reduction"].append(
                            state.nonpermanent_cost_reduction
                        )
                        game_records[rg]["permanent cost reduction"].append(
                            state.permanent_cost_reduction
                        )
                        game_records[rg]["spell cost reduction"].append(
                            state.spell_cost_reduction
                        )
                        game_records[rg]["creature cost reduction"].append(
                            state.creature_cost_reduction
                        )
                        game_records[rg]["starting hand land count"].append(
                            state.starting_hand_land_count
                        )
                        game_records[rg]["per turn effects"].append(
                            [c.unique_name for c, _ in state.per_turn_effects]
                        )
                        game_records[rg]["cast triggers"].append(
                            [c.unique_name for c, _ in state.cast_triggers]
                        )
                        game_records[rg]["starting hand"].append(
                            [c.unique_name for c in state.starting_hand]
                        )
                        game_records[rg]["played cards"].append(
                            [c.unique_name for c in all_cards_played]
                        )

            if self.verbose:
                for line in state.log:
                    print(line)
                print(f"\n### Game {j + 1} finished")

        # Compute summary stats
        import bisect

        mean_mana = float(np.mean(mana_spent_list))
        mean_lands = float(np.mean(lands_played_list))
        mean_mulls = float(np.mean(mulls_list))
        mean_draws = float(np.mean(cards_drawn_list))
        mean_bad_turns = float(np.mean(bad_turns_list))
        mean_mid_turns = float(np.mean(mid_turns_list))
        percentile_25 = float(np.percentile(mana_spent_list, 25))
        percentile_50 = float(np.percentile(mana_spent_list, 50))
        percentile_75 = float(np.percentile(mana_spent_list, 75))

        total_mana = float(np.sum(mana_spent_list))
        sorted_mana = sorted(mana_spent_list)
        cumulative_mana = np.cumsum(sorted_mana)

        con_threshold = 0.25
        threshold_index = bisect.bisect_left(cumulative_mana, total_mana * con_threshold)
        threshold_percent = threshold_index / len(mana_spent_list)
        threshold_mana = float(sorted_mana[threshold_index])
        consistency = (1 - threshold_percent) / (1 - con_threshold)

        total_recorded = self.sims - sample_games
        distribution_stats = {
            "top_centile": len(game_records["top_centile"]["mana"]) / total_recorded if self.record_centile else 0,
            "top_decile": len(game_records["top_decile"]["mana"]) / total_recorded if self.record_decile else 0,
            "top_quartile": len(game_records["top_quartile"]["mana"]) / total_recorded if self.record_quartile else 0,
            "top_half": len(game_records["top_half"]["mana"]) / total_recorded if self.record_half else 0,
            "low_half": len(game_records["low_half"]["mana"]) / total_recorded if self.record_half else 0,
            "low_quartile": len(game_records["low_quartile"]["mana"]) / total_recorded if self.record_quartile else 0,
            "low_decile": len(game_records["low_decile"]["mana"]) / total_recorded if self.record_decile else 0,
            "low_centile": len(game_records["low_centile"]["mana"]) / total_recorded if self.record_centile else 0,
        }

        return SimulationResult(
            land_count=self.land_count,
            mean_mana=mean_mana,
            consistency=consistency,
            mean_bad_turns=mean_bad_turns,
            mean_mid_turns=mean_mid_turns,
            mean_lands=mean_lands,
            mean_mulls=mean_mulls,
            mean_draws=mean_draws,
            percentile_25=percentile_25,
            percentile_50=percentile_50,
            percentile_75=percentile_75,
            threshold_percent=threshold_percent,
            threshold_mana=threshold_mana,
            con_threshold=con_threshold,
            distribution_stats=distribution_stats,
            game_records=dict(game_records),
        )
