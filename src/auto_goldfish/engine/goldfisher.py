"""Core goldfishing simulation engine.

Refactored to use the effects system, GameState, and Card dataclass.
No CLI code here -- returns structured ``SimulationResult``.
"""

from __future__ import annotations

import os
import random
from collections import defaultdict
try:
    from concurrent.futures import ProcessPoolExecutor
except ImportError:
    ProcessPoolExecutor = None  # type: ignore[misc,assignment]

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(iterable, **_kwargs):  # type: ignore[misc]
        """No-op fallback when tqdm is unavailable (e.g. Pyodide)."""
        return iterable

from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.effects.registry import CardEffects, EffectRegistry
from auto_goldfish.effects.types import CastTriggerEffect, ManaFunctionEffect, OnPlayEffect, PerTurnEffect
from auto_goldfish.engine.mana import land_mana, mana_rocks
from auto_goldfish.engine.mulligan import DefaultMulligan, MulliganStrategy
from auto_goldfish.models.card import Card
from auto_goldfish.models.game_state import GameState


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
    mean_spells_cast: float = 0.0
    percentile_25: float = 0.0
    percentile_50: float = 0.0
    percentile_75: float = 0.0
    threshold_percent: float = 0.0
    threshold_mana: float = 0.0
    con_threshold: float = 0.25
    distribution_stats: Dict[str, float] = field(default_factory=dict)
    card_performance: Dict[str, Any] = field(default_factory=dict)
    game_records: Dict[str, Dict[str, list]] = field(default_factory=dict)
    replay_data: Dict[str, Any] = field(default_factory=dict)

    # 95% confidence intervals (low, high)
    ci_mean_mana: Tuple[float, float] = (0.0, 0.0)
    ci_consistency: Tuple[float, float] = (0.0, 0.0)
    ci_mean_bad_turns: Tuple[float, float] = (0.0, 0.0)

    def as_row(self) -> list:
        """Return a flat list for tabulate (without distribution_stats)."""
        mana_margin = (self.ci_mean_mana[1] - self.ci_mean_mana[0]) / 2
        con_margin = (self.ci_consistency[1] - self.ci_consistency[0]) / 2
        return [
            self.land_count,
            f"{self.mean_mana:.2f} +/-{mana_margin:.2f}",
            f"{self.consistency:.4f} +/-{con_margin:.4f}",
            self.mean_bad_turns,
            self.mean_mid_turns,
            self.mean_lands,
            self.mean_mulls,
            self.mean_draws,
            self.mean_spells_cast,
            self.percentile_25,
            self.percentile_50,
            self.percentile_75,
            self.threshold_percent,
            self.threshold_mana,
        ]


# ---------------------------------------------------------------------------
# Module-level helpers (used by effects via import)
# ---------------------------------------------------------------------------


def _draw(state: GameState) -> None:
    """Draw a card from the deck into the hand."""
    if not state.deck:
        if state.should_log:
            state.log.append("Draw failed, deck is empty")
        state.draws += 1
        return
    drawn_i = state.deck.pop()
    drawn = state.decklist[drawn_i]
    drawn.zone = state.hand
    state.hand.append(drawn_i)
    state.draws += 1
    if state.should_log:
        state.log.append(f"Draw {drawn.printable}")


def _random_discard(state: GameState) -> None:
    """Discard a random card from hand."""
    discarded_i = random.choice(state.hand)
    discarded = state.decklist[discarded_i]
    discarded.change_zone(state.yard)
    if state.should_log:
        state.log.append(f"Discarded {discarded.printable}")


def _find_effectless_lands(state: GameState, count: int) -> list[int]:
    """Find up to *count* land cards in the deck that have no registered effects."""
    found: list[int] = []
    for idx in state.deck:
        card = state.decklist[idx]
        if card.land and not _has_effects(card):
            found.append(idx)
            if len(found) >= count:
                break
    return found


def _has_effects(card: Card) -> bool:
    """Return True if the card has any cached effects."""
    eff = getattr(card, '_cached_effects', None)
    if eff is None:
        return False
    return bool(eff.on_play or eff.per_turn or eff.cast_trigger or eff.mana_function)


def _card_to_dict(card: Card) -> dict:
    """Serialize a Card back to a dict for worker reconstruction."""
    return {
        "name": card.name, "quantity": card.quantity,
        "oracle_cmc": card.oracle_cmc, "cmc": card.cmc,
        "cost": card.cost, "text": card.text,
        "sub_types": card.sub_types, "super_types": card.super_types,
        "types": card.types, "identity": card.identity,
        "default_category": card.default_category,
        "user_category": card.user_category,
        "tag": card.tag, "commander": card.commander,
    }


_REPLAY_CAP_PER_WORKER = 15


def _worker_run_batch(
    deck_dicts: list[dict],
    turns: int,
    n_games: int,
    base_seed: int | None,
    game_offset: int,
    capture_replays: bool = False,
) -> dict:
    """Top-level function for ProcessPoolExecutor workers.

    Creates a fresh Goldfisher and runs ``n_games`` simulations.
    Returns raw per-game stats as lists.

    When *capture_replays* is ``True`` the worker records unclassified
    turn-by-turn snapshots for a sample of games (up to
    ``_REPLAY_CAP_PER_WORKER``).  Classification into quartile buckets
    happens later in ``_run_parallel`` once the full mana distribution
    is available.
    """
    gf = Goldfisher(
        deck_dicts, turns=turns, sims=n_games,
        record_results=None, seed=base_seed,
    )
    # Adjust seed offset so each batch uses the correct per-game seeds
    mana_spent = []
    mulls = []
    lands_played = []
    cards_drawn = []
    spells_cast = []
    bad_turns = []
    mid_turns = []
    card_cast_turns: list[list] = [[] for _ in gf.decklist]
    played_cards_per_game: list[set] = []

    # Unclassified replay snapshots: list of (total_mana, replay_dict)
    raw_replays: list[tuple[int, dict]] = []
    # Start capturing after the first 10% of games to get some variance
    replay_start = max(int(n_games * 0.1), 1)

    for j in range(n_games):
        global_j = game_offset + j
        if base_seed is not None:
            random.seed(base_seed + global_j)
        state = gf._reset()
        mulligans = gf._mulligan(state)

        total_mana_spent = 0
        game_lands = 0
        game_bad = 0
        game_mid = 0
        game_spells_cast = 0

        # Decide whether to capture this game's replay
        _capture_this = (
            capture_replays
            and j >= replay_start
            and len(raw_replays) < _REPLAY_CAP_PER_WORKER
        )
        turn_snapshots: list[dict] = []
        starting_hand_names: list[str] = []
        if _capture_this:
            starting_hand_names = [gf.decklist[idx].name for idx in state.hand]

        for i in range(turns):
            turn_mana = 0
            spells_played = 0

            if _capture_this:
                hand_before = [gf.decklist[idx].name for idx in state.hand]

            played = gf._take_turn(state)
            for card in played:
                if not card.ramp:
                    turn_mana += card.mana_spent_when_played
                if card.land:
                    game_lands += 1
                if card.spell:
                    spells_played += 1
            game_spells_cast += spells_played
            if spells_played == 0 and state.deck:
                game_bad += 1
            if spells_played < 2 and state.deck and turn_mana < i + 1:
                game_mid += 1
            total_mana_spent += turn_mana

            if _capture_this:
                turn_snapshots.append({
                    "turn": i + 1,
                    "hand_before_draw": hand_before,
                    "played": [
                        {
                            "name": c.name,
                            "cost": c.cost,
                            "mana_spent": c.mana_spent_when_played,
                            "is_land": c.land,
                        }
                        for c in played
                    ],
                    "mana_spent_this_turn": turn_mana,
                    "total_mana_production": gf._get_mana(state),
                    "hand_after": [gf.decklist[idx].name for idx in state.hand],
                    "battlefield": [gf.decklist[idx].name for idx in state.battlefield],
                    "lands": [gf.decklist[idx].name for idx in state.lands],
                    "graveyard": [gf.decklist[idx].name for idx in state.yard],
                })

        mana_spent.append(total_mana_spent)
        lands_played.append(game_lands)
        mulls.append(mulligans)
        cards_drawn.append(state.draws)
        spells_cast.append(game_spells_cast)
        bad_turns.append(game_bad)
        mid_turns.append(game_mid)

        game_played = set()
        for k, turn in enumerate(state.card_cast_turn):
            if turn is not None and not gf.decklist[k].land:
                card_cast_turns[k].append(turn)
                if gf.decklist[k].spell:
                    game_played.add(k)
        played_cards_per_game.append(game_played)

        if _capture_this:
            raw_replays.append((total_mana_spent, {
                "total_mana": total_mana_spent,
                "mulligans": mulligans,
                "starting_hand": starting_hand_names,
                "turns": turn_snapshots,
            }))

    result: dict = {
        "mana_spent": mana_spent,
        "mulls": mulls,
        "lands_played": lands_played,
        "cards_drawn": cards_drawn,
        "spells_cast": spells_cast,
        "bad_turns": bad_turns,
        "mid_turns": mid_turns,
        "card_cast_turns": card_cast_turns,
        "played_cards_per_game": played_cards_per_game,
    }
    if capture_replays:
        result["raw_replays"] = raw_replays
    return result


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
        workers: int = 1,
        **kwargs,
    ):
        self.registry = registry or DEFAULT_REGISTRY
        self.mulligan_strategy = mulligan_strategy or DefaultMulligan()
        self.turns = turns
        self.sims = sims
        self.verbose = verbose
        self.seed = seed
        self.workers = workers
        self._should_log = verbose or record_results is not None

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

        # Save original state for optimizer restore
        self._original_decklist_dicts = list(non_commander_dicts)
        self._original_registry = self.registry
        self._original_land_count = self.land_count

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

        # Cache registry effects on the card to avoid repeated lookups
        card._cached_effects = effects

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
        state.should_log = self._should_log
        state.card_cast_turn = [None] * len(self.decklist)
        state.decklist = self.decklist
        state.deckdict = self.deckdict

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

            if state.should_log:
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
        if state.should_log:
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

        if state.should_log:
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
                if state.should_log:
                    state.log.append(f"Played as land {land.printable}")
                land.mana_spent_when_played = 0
                played.append(land)
                state.played_land_this_turn += 1
                if not land.tapped:
                    state.untapped_land_this_turn += 1

                # Apply on_play effects for lands
                effects = land._cached_effects
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
                    effects = card._cached_effects
                    if effects:
                        for eff in effects.cast_trigger:
                            state.cast_triggers.append((card, eff))
                        for eff in effects.per_turn:
                            state.per_turn_effects.append((card, eff))
                        for eff in effects.mana_function:
                            state.mana_functions.append(eff)

                    # Execute on_play effects
                    if state.should_log:
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
            if state.should_log:
                state.log.append(f"Spent treasures: [{state.treasure}] -> [{mana_available}]")
            state.treasure = mana_available

        return played_effects

    def _take_turn(self, state: GameState) -> list[Card]:
        """Execute one turn."""
        if state.should_log:
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
        from auto_goldfish.decklist.loader import get_basic_island

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

    def restore_original_decklist(self) -> None:
        """Reset decklist to its original state (before any set_lands or optimizer modifications)."""
        self.registry = self._original_registry
        self.decklist = [
            self._make_card(d, i) for i, d in enumerate(self._original_decklist_dicts)
        ]
        self.deckdict = {c.name: c for c in self.decklist}
        self.land_count = self._original_land_count

    def _compute_distribution_stats(self, mana_spent_list: list) -> Dict[str, float]:
        """Compute distribution bucket fractions from raw mana data.

        Uses the first 10% (min 100) games to calibrate percentile thresholds,
        then counts what fraction of remaining games fall into each bucket.
        """
        sample_games = int(max(len(mana_spent_list) / 10, 100))
        if sample_games >= len(mana_spent_list):
            # Not enough data for calibration
            return {k: 0.0 for k in [
                "top_centile", "top_decile", "top_quartile", "top_half",
                "low_half", "low_quartile", "low_decile", "low_centile",
            ]}

        calibration = mana_spent_list[:sample_games]
        evaluation = mana_spent_list[sample_games:]

        top_centile_threshold = float(np.percentile(calibration, 99))
        low_centile_threshold = float(np.percentile(calibration, 1))
        top_decile_threshold = float(np.percentile(calibration, 90))
        low_decile_threshold = float(np.percentile(calibration, 10))
        top_quartile_threshold = float(np.percentile(calibration, 75))
        low_quartile_threshold = float(np.percentile(calibration, 25))
        median_threshold = float(np.percentile(calibration, 50))

        counts = {k: 0 for k in [
            "top_centile", "top_decile", "top_quartile", "top_half",
            "low_half", "low_quartile", "low_decile", "low_centile",
        ]}

        for mana in evaluation:
            if self.record_centile and mana >= top_centile_threshold:
                counts["top_centile"] += 1
            if self.record_decile and mana >= top_decile_threshold:
                counts["top_decile"] += 1
            if self.record_quartile and mana >= top_quartile_threshold:
                counts["top_quartile"] += 1
            if self.record_half and mana >= median_threshold:
                counts["top_half"] += 1

            if self.record_centile and mana <= low_centile_threshold:
                counts["low_centile"] += 1
            if self.record_decile and mana <= low_decile_threshold:
                counts["low_decile"] += 1
            if self.record_quartile and mana <= low_quartile_threshold:
                counts["low_quartile"] += 1
            if self.record_half and mana < median_threshold:
                counts["low_half"] += 1

        total = len(evaluation)
        return {k: v / total for k, v in counts.items()}

    def _compute_card_performance(
        self,
        mana_spent_list: list,
        played_cards_per_game: list[set],
    ) -> Dict[str, Any]:
        """Compute which cards are overrepresented in high/low performance games.

        Uses calibration sample (first 10%, min 100) to set quartile thresholds,
        then classifies remaining games.
        """
        if len(mana_spent_list) < 100:
            return {}

        sample_size = int(max(len(mana_spent_list) / 10, 100))
        if sample_size >= len(mana_spent_list):
            return {}

        calibration = mana_spent_list[:sample_size]
        top_threshold = float(np.percentile(calibration, 75))
        low_threshold = float(np.percentile(calibration, 25))

        # Classify evaluation games
        top_games = []
        low_games = []
        for i in range(sample_size, len(mana_spent_list)):
            mana = mana_spent_list[i]
            if mana >= top_threshold:
                top_games.append(i)
            if mana <= low_threshold:
                low_games.append(i)

        if not top_games or not low_games:
            return {}

        # Count card appearances in each bucket
        card_top_count: Dict[int, int] = defaultdict(int)
        card_low_count: Dict[int, int] = defaultdict(int)

        for gi in top_games:
            for card_idx in played_cards_per_game[gi]:
                card_top_count[card_idx] += 1

        for gi in low_games:
            for card_idx in played_cards_per_game[gi]:
                card_low_count[card_idx] += 1

        n_top = len(top_games)
        n_low = len(low_games)

        # Score each non-land spell card
        scores = []
        for k, card in enumerate(self.decklist):
            if card.land or not card.spell:
                continue
            top_rate = card_top_count.get(k, 0) / n_top
            low_rate = card_low_count.get(k, 0) / n_low
            score = top_rate - low_rate

            effects_desc = ""
            if card._cached_effects:
                effects_desc = card._cached_effects.describe_effects()

            scores.append({
                "name": card.name,
                "cost": card.cost,
                "cmc": card.cmc,
                "effects": effects_desc,
                "top_rate": round(top_rate, 4),
                "low_rate": round(low_rate, 4),
                "score": round(score, 4),
            })

        # Sort and pick top/bottom 10
        high_performing = sorted(scores, key=lambda x: x["score"], reverse=True)[:10]
        low_performing = sorted(scores, key=lambda x: x["score"])[:10]

        return {
            "high_performing": high_performing,
            "low_performing": low_performing,
            "total_top_games": n_top,
            "total_low_games": n_low,
        }

    def _get_deck_dicts(self) -> list[dict]:
        """Serialize current decklist + commanders to dicts for workers."""
        dicts = [_card_to_dict(c) for c in self.commanders]
        dicts.extend(_card_to_dict(c) for c in self.decklist)
        return dicts

    def _run_parallel(self) -> dict:
        """Run simulations across multiple worker processes."""
        deck_dicts = self._get_deck_dicts()
        num_workers = min(self.workers, self.sims)
        batch_size = self.sims // num_workers
        remainder = self.sims % num_workers

        futures = []
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            offset = 0
            for w in range(num_workers):
                n = batch_size + (1 if w < remainder else 0)
                futures.append(
                    executor.submit(
                        _worker_run_batch,
                        deck_dicts, self.turns, n, self.seed, offset,
                        capture_replays=True,
                    )
                )
                offset += n

        # Merge results from all workers
        merged = {
            "mana_spent": [], "mulls": [], "lands_played": [],
            "cards_drawn": [], "spells_cast": [], "bad_turns": [], "mid_turns": [],
            "played_cards_per_game": [],
        }
        card_cast_turns: list[list] = [[] for _ in self.decklist]
        all_raw_replays: list[tuple[int, dict]] = []

        for future in futures:
            batch = future.result()
            for key in ["mana_spent", "mulls", "lands_played",
                        "cards_drawn", "spells_cast", "bad_turns", "mid_turns"]:
                merged[key].extend(batch[key])
            for k, turns_list in enumerate(batch["card_cast_turns"]):
                card_cast_turns[k].extend(turns_list)
            merged["played_cards_per_game"].extend(batch["played_cards_per_game"])
            all_raw_replays.extend(batch.get("raw_replays", []))

        merged["card_cast_turns"] = card_cast_turns

        # Classify pooled replays using the full mana distribution
        replay_buckets: dict[str, list] = {"top": [], "mid": [], "low": []}
        if all_raw_replays and merged["mana_spent"]:
            top_threshold = float(np.percentile(merged["mana_spent"], 75))
            low_threshold = float(np.percentile(merged["mana_spent"], 25))
            for mana_val, replay in all_raw_replays:
                if mana_val >= top_threshold:
                    if len(replay_buckets["top"]) < 10:
                        replay_buckets["top"].append(replay)
                elif mana_val <= low_threshold:
                    if len(replay_buckets["low"]) < 10:
                        replay_buckets["low"].append(replay)
                else:
                    if len(replay_buckets["mid"]) < 10:
                        replay_buckets["mid"].append(replay)
        merged["replay_data"] = replay_buckets
        return merged

    def _simulate_from_raw(self, raw: dict) -> SimulationResult:
        """Compute summary stats from raw per-game data (used by parallel path)."""
        import bisect

        mana_spent_list = raw["mana_spent"]
        lands_played_list = raw["lands_played"]
        mulls_list = raw["mulls"]
        cards_drawn_list = raw["cards_drawn"]
        spells_cast_list = raw["spells_cast"]
        bad_turns_list = raw["bad_turns"]
        mid_turns_list = raw["mid_turns"]

        mean_mana = float(np.mean(mana_spent_list))
        mean_lands = float(np.mean(lands_played_list))
        mean_mulls = float(np.mean(mulls_list))
        mean_draws = float(np.mean(cards_drawn_list))
        mean_spells_cast = float(np.mean(spells_cast_list))
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

        n = len(mana_spent_list)
        z = 1.96

        mana_se = float(np.std(mana_spent_list, ddof=1) / np.sqrt(n))
        ci_mean_mana = (mean_mana - z * mana_se, mean_mana + z * mana_se)

        bad_se = float(np.std(bad_turns_list, ddof=1) / np.sqrt(n))
        ci_mean_bad_turns = (mean_bad_turns - z * bad_se, mean_bad_turns + z * bad_se)

        n_boot = min(1000, n)
        boot_consistencies = []
        mana_arr = np.array(mana_spent_list)
        for _ in range(n_boot):
            boot_sample = np.random.choice(mana_arr, size=n, replace=True)
            boot_total = float(np.sum(boot_sample))
            boot_sorted = np.sort(boot_sample)
            boot_cum = np.cumsum(boot_sorted)
            boot_idx = int(np.searchsorted(boot_cum, boot_total * con_threshold))
            boot_pct = boot_idx / n
            boot_consistencies.append((1 - boot_pct) / (1 - con_threshold))
        ci_consistency = (
            float(np.percentile(boot_consistencies, 2.5)),
            float(np.percentile(boot_consistencies, 97.5)),
        )

        # Compute distribution stats (same calibration approach as sequential path)
        distribution_stats = self._compute_distribution_stats(mana_spent_list)

        # Compute card performance
        played_cards_per_game = raw.get("played_cards_per_game", [])
        card_performance = self._compute_card_performance(mana_spent_list, played_cards_per_game)

        replay_data = raw.get("replay_data", {})

        return SimulationResult(
            land_count=self.land_count,
            mean_mana=mean_mana,
            consistency=consistency,
            mean_bad_turns=mean_bad_turns,
            mean_mid_turns=mean_mid_turns,
            mean_lands=mean_lands,
            mean_mulls=mean_mulls,
            mean_draws=mean_draws,
            mean_spells_cast=mean_spells_cast,
            percentile_25=percentile_25,
            percentile_50=percentile_50,
            percentile_75=percentile_75,
            threshold_percent=threshold_percent,
            threshold_mana=threshold_mana,
            con_threshold=con_threshold,
            ci_mean_mana=ci_mean_mana,
            ci_consistency=ci_consistency,
            ci_mean_bad_turns=ci_mean_bad_turns,
            distribution_stats=distribution_stats,
            card_performance=card_performance,
            replay_data=replay_data,
        )

    def simulate(self, progress_callback=None) -> SimulationResult:
        """Run all simulations and return a ``SimulationResult``.

        Args:
            progress_callback: Optional callable(current, total) for progress updates.
        """
        if self.workers > 1 and ProcessPoolExecutor is not None:
            return self._simulate_from_raw(self._run_parallel())

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
        spells_cast_list = []
        bad_turns_list = []
        mid_turns_list = []
        card_cast_turn_list: list[list] = [[] for _ in self.decklist]
        played_cards_per_game: list[set] = []
        replay_buckets: dict[str, list] = {"top": [], "mid": [], "low": []}

        game_iter = range(self.sims)
        if progress_callback is None:
            game_iter = tqdm(game_iter, leave=False)

        for j in game_iter:
            if progress_callback is not None:
                progress_callback(j, self.sims)
            if self.seed is not None:
                random.seed(self.seed + j)
            state = self._reset()
            mulligans = self._mulligan(state)

            total_mana_spent = 0
            lands_played = 0
            bad_turns = 0
            mid_turns = 0
            total_spells_cast = 0
            all_cards_played: list[Card] = []

            # Replay capture: only when thresholds are available and buckets not full
            _capture_replay = (
                top_centile_threshold is not None
                and not all(len(b) >= 10 for b in replay_buckets.values())
            )
            turn_snapshots: list[dict] = []
            starting_hand_names: list[str] = []
            if _capture_replay:
                starting_hand_names = [self.decklist[idx].name for idx in state.hand]

            for i in range(self.turns):
                mana_spent = 0
                spells_played = 0

                if _capture_replay:
                    hand_before = [self.decklist[idx].name for idx in state.hand]

                played = self._take_turn(state)

                for card in played:
                    all_cards_played.append(card)
                    if not card.ramp:
                        mana_spent += card.mana_spent_when_played
                    if card.land:
                        lands_played += 1
                    if card.spell:
                        spells_played += 1

                total_spells_cast += spells_played
                if spells_played == 0 and state.deck:
                    bad_turns += 1
                if spells_played < 2 and state.deck and mana_spent < i + 1:
                    mid_turns += 1
                total_mana_spent += mana_spent

                if _capture_replay:
                    turn_snapshots.append({
                        "turn": i + 1,
                        "hand_before_draw": hand_before,
                        "played": [
                            {
                                "name": c.name,
                                "cost": c.cost,
                                "mana_spent": c.mana_spent_when_played,
                                "is_land": c.land,
                            }
                            for c in played
                        ],
                        "mana_spent_this_turn": mana_spent,
                        "total_mana_production": self._get_mana(state),
                        "hand_after": [self.decklist[idx].name for idx in state.hand],
                        "battlefield": [self.decklist[idx].name for idx in state.battlefield],
                        "lands": [self.decklist[idx].name for idx in state.lands],
                        "graveyard": [self.decklist[idx].name for idx in state.yard],
                    })

            mana_spent_list.append(total_mana_spent)
            lands_played_list.append(lands_played)
            mulls_list.append(mulligans)
            cards_drawn_list.append(state.draws)
            spells_cast_list.append(total_spells_cast)
            bad_turns_list.append(bad_turns)
            mid_turns_list.append(mid_turns)

            game_played = set()
            for k, turn in enumerate(state.card_cast_turn):
                if turn is not None and not self.decklist[k].land:
                    card_cast_turn_list[k].append(turn)
                    if self.decklist[k].spell:
                        game_played.add(k)
            played_cards_per_game.append(game_played)

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

            # Classify game into replay buckets
            if _capture_replay:
                game_replay = {
                    "total_mana": total_mana_spent,
                    "mulligans": mulligans,
                    "starting_hand": starting_hand_names,
                    "turns": turn_snapshots,
                }
                if total_mana_spent >= top_quartile_threshold:
                    if len(replay_buckets["top"]) < 10:
                        replay_buckets["top"].append(game_replay)
                elif total_mana_spent <= low_quartile_threshold:
                    if len(replay_buckets["low"]) < 10:
                        replay_buckets["low"].append(game_replay)
                else:
                    if len(replay_buckets["mid"]) < 10:
                        replay_buckets["mid"].append(game_replay)

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
        mean_spells_cast = float(np.mean(spells_cast_list))
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

        # Compute 95% confidence intervals (normal approximation)
        n = len(mana_spent_list)
        z = 1.96

        mana_se = float(np.std(mana_spent_list, ddof=1) / np.sqrt(n))
        ci_mean_mana = (mean_mana - z * mana_se, mean_mana + z * mana_se)

        bad_se = float(np.std(bad_turns_list, ddof=1) / np.sqrt(n))
        ci_mean_bad_turns = (mean_bad_turns - z * bad_se, mean_bad_turns + z * bad_se)

        # Bootstrap CI for consistency (not directly a sample mean)
        n_boot = min(1000, n)
        boot_consistencies = []
        mana_arr = np.array(mana_spent_list)
        for _ in range(n_boot):
            boot_sample = np.random.choice(mana_arr, size=n, replace=True)
            boot_total = float(np.sum(boot_sample))
            boot_sorted = np.sort(boot_sample)
            boot_cum = np.cumsum(boot_sorted)
            boot_idx = int(np.searchsorted(boot_cum, boot_total * con_threshold))
            boot_pct = boot_idx / n
            boot_consistencies.append((1 - boot_pct) / (1 - con_threshold))
        ci_consistency = (
            float(np.percentile(boot_consistencies, 2.5)),
            float(np.percentile(boot_consistencies, 97.5)),
        )

        distribution_stats = self._compute_distribution_stats(mana_spent_list)
        card_performance = self._compute_card_performance(mana_spent_list, played_cards_per_game)

        return SimulationResult(
            land_count=self.land_count,
            mean_mana=mean_mana,
            consistency=consistency,
            mean_bad_turns=mean_bad_turns,
            mean_mid_turns=mean_mid_turns,
            mean_lands=mean_lands,
            mean_mulls=mean_mulls,
            mean_draws=mean_draws,
            mean_spells_cast=mean_spells_cast,
            percentile_25=percentile_25,
            percentile_50=percentile_50,
            percentile_75=percentile_75,
            threshold_percent=threshold_percent,
            threshold_mana=threshold_mana,
            con_threshold=con_threshold,
            distribution_stats=distribution_stats,
            card_performance=card_performance,
            game_records=dict(game_records),
            replay_data=replay_buckets,
            ci_mean_mana=ci_mean_mana,
            ci_consistency=ci_consistency,
            ci_mean_bad_turns=ci_mean_bad_turns,
        )
