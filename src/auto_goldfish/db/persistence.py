"""Persistence helpers -- get-or-create patterns and convenience wrappers."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CardPerformanceRow,
    CardRow,
    DeckCardRow,
    DeckRow,
    EffectLabelRow,
    SimulationResultRow,
    SimulationRunRow,
)
from .session import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# get-or-create primitives
# ---------------------------------------------------------------------------

def get_or_create_card(session: Session, name: str) -> CardRow:
    row = session.execute(select(CardRow).where(CardRow.name == name)).scalar_one_or_none()
    if row is None:
        row = CardRow(name=name)
        session.add(row)
        session.flush()
    return row


def get_or_create_effect_label(session: Session, effects: dict) -> EffectLabelRow:
    canonical = json.dumps(effects, sort_keys=True)
    # Compare against the canonical JSON form
    row = session.execute(
        select(EffectLabelRow).where(EffectLabelRow.effects_json == json.loads(canonical))
    ).scalar_one_or_none()
    if row is None:
        row = EffectLabelRow(effects_json=json.loads(canonical))
        session.add(row)
        session.flush()
    return row


def get_or_create_deck(session: Session, name: str) -> DeckRow:
    row = session.execute(select(DeckRow).where(DeckRow.name == name)).scalar_one_or_none()
    if row is None:
        row = DeckRow(name=name)
        session.add(row)
        session.flush()
    return row


# ---------------------------------------------------------------------------
# Deck card persistence
# ---------------------------------------------------------------------------

def save_deck_cards(
    session: Session,
    deck: DeckRow,
    card_effects_list: List[Dict[str, Any]],
    overrides: Dict[str, Any],
) -> None:
    """Upsert deck cards with their effect labels and override status."""
    for entry in card_effects_list:
        card_name = entry.get("name", "")
        if not card_name:
            continue

        card = get_or_create_card(session, card_name)

        # Determine effect label
        label: Optional[EffectLabelRow] = None
        user_edited = False
        if card_name in overrides and overrides[card_name]:
            label = get_or_create_effect_label(session, overrides[card_name])
            user_edited = True
        elif entry.get("registry_override"):
            label = get_or_create_effect_label(session, entry["registry_override"])

        # Upsert deck_card
        existing = session.execute(
            select(DeckCardRow).where(
                DeckCardRow.deck_id == deck.id,
                DeckCardRow.card_id == card.id,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(DeckCardRow(
                deck_id=deck.id,
                card_id=card.id,
                label_id=label.id if label else None,
                user_edited=user_edited,
            ))
        else:
            existing.label_id = label.id if label else None
            existing.user_edited = user_edited

    session.flush()


# ---------------------------------------------------------------------------
# Simulation run persistence
# ---------------------------------------------------------------------------

def save_simulation_run(
    session: Session,
    job_id: str,
    deck: DeckRow,
    config: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> SimulationRunRow:
    """Save a complete simulation run with results and card performance."""

    # Determine optimal land count (highest consistency)
    optimal_land_count = None
    if results:
        best = max(results, key=lambda r: r.get("consistency", 0))
        optimal_land_count = best.get("land_count")

    run = SimulationRunRow(
        job_id=job_id,
        deck_id=deck.id,
        turns=config.get("turns", 10),
        sims=config.get("sims", 1000),
        min_lands=config.get("min_lands", 36),
        max_lands=config.get("max_lands", 39),
        seed=config.get("seed"),
        mulligan_strategy=config.get("mulligan", "default"),
        optimal_land_count=optimal_land_count,
    )
    session.add(run)
    session.flush()

    # Save per-land-count results
    for r in results:
        ci_mana = r.get("ci_mean_mana", [0.0, 0.0])
        ci_con = r.get("ci_consistency", [0.0, 0.0])
        session.add(SimulationResultRow(
            run_id=run.id,
            land_count=r.get("land_count", 0),
            mean_mana=r.get("mean_mana", 0.0),
            mean_draws=r.get("mean_draws", 0.0),
            mean_bad_turns=r.get("mean_bad_turns", 0.0),
            mean_lands=r.get("mean_lands", 0.0),
            mean_mulls=r.get("mean_mulls", 0.0),
            ci_mean_mana_low=ci_mana[0] if len(ci_mana) > 0 else 0.0,
            ci_mean_mana_high=ci_mana[1] if len(ci_mana) > 1 else 0.0,
            consistency=r.get("consistency", 0.0),
            ci_consistency_low=ci_con[0] if len(ci_con) > 0 else 0.0,
            ci_consistency_high=ci_con[1] if len(ci_con) > 1 else 0.0,
            percentile_25=r.get("percentile_25", 0.0),
            percentile_50=r.get("percentile_50", 0.0),
            percentile_75=r.get("percentile_75", 0.0),
        ))

    # Save card performance only at optimal land count (bottom 10 with effects)
    if optimal_land_count is not None:
        optimal_result = next(
            (r for r in results if r.get("land_count") == optimal_land_count),
            None,
        )
        if optimal_result:
            perf = optimal_result.get("card_performance", {})
            low_performing = perf.get("low_performing", [])

            # Filter to cards that have a non-empty effects description
            cards_with_effects = [
                c for c in low_performing if c.get("effects", "").strip()
            ]

            for rank, card_data in enumerate(cards_with_effects[:10], start=1):
                card = get_or_create_card(session, card_data["name"])
                session.add(CardPerformanceRow(
                    run_id=run.id,
                    card_id=card.id,
                    top_rate=card_data.get("top_rate", 0.0),
                    low_rate=card_data.get("low_rate", 0.0),
                    score=card_data.get("score", 0.0),
                    rank=rank,
                ))

    session.flush()
    return run


# ---------------------------------------------------------------------------
# Convenience wrappers (handle session internally)
# ---------------------------------------------------------------------------

def persist_completed_job(job: Any) -> None:
    """Persist a completed SimJob to the database.

    Called from simulation_runner after job.status = "completed".
    """
    with get_session() as session:
        deck = get_or_create_deck(session, job.deck_name)
        save_simulation_run(session, job.job_id, deck, job.config, job.results)
    logger.info("Persisted simulation run %s for deck %s", job.job_id, job.deck_name)


def persist_deck_cards(
    deck_name: str,
    card_effects_list: List[Dict[str, Any]],
    overrides: Dict[str, Any],
) -> None:
    """Persist deck card labels to the database.

    Called from the config route after building card_effects_list.
    """
    with get_session() as session:
        deck = get_or_create_deck(session, deck_name)
        save_deck_cards(session, deck, card_effects_list, overrides)
    logger.info("Persisted deck cards for %s", deck_name)
