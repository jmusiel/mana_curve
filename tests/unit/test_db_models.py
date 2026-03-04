"""Tests for DB models -- schema creation, unique constraints."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from auto_goldfish.db.models import (
    Base,
    CardPerformanceRow,
    CardRow,
    DeckCardRow,
    DeckRow,
    EffectLabelRow,
    SimulationResultRow,
    SimulationRunRow,
)


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestCreateAll:
    """Verify all tables are created without errors."""

    def test_tables_created(self, db_session: Session):
        tables = Base.metadata.tables.keys()
        assert "cards" in tables
        assert "effect_labels" in tables
        assert "decks" in tables
        assert "deck_cards" in tables
        assert "simulation_runs" in tables
        assert "simulation_results" in tables
        assert "card_performance" in tables


class TestCardRow:
    def test_insert_card(self, db_session: Session):
        card = CardRow(name="Sol Ring")
        db_session.add(card)
        db_session.commit()
        assert card.id is not None
        assert card.name == "Sol Ring"

    def test_unique_name(self, db_session: Session):
        db_session.add(CardRow(name="Sol Ring"))
        db_session.commit()
        db_session.add(CardRow(name="Sol Ring"))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestEffectLabelRow:
    def test_insert_label(self, db_session: Session):
        label = EffectLabelRow(effects_json='{"effects": [{"slot": "on_play", "type": "draw"}]}')
        db_session.add(label)
        db_session.commit()
        assert label.id is not None

    def test_unique_json(self, db_session: Session):
        data = '{"effects": [{"type": "draw"}]}'
        db_session.add(EffectLabelRow(effects_json=data))
        db_session.commit()
        db_session.add(EffectLabelRow(effects_json=data))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestDeckRow:
    def test_insert_deck(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        db_session.add(deck)
        db_session.commit()
        assert deck.id is not None
        assert deck.created_at is not None

    def test_unique_name(self, db_session: Session):
        db_session.add(DeckRow(name="test-deck"))
        db_session.commit()
        db_session.add(DeckRow(name="test-deck"))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestDeckCardRow:
    def test_unique_deck_card(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        card = CardRow(name="Sol Ring")
        db_session.add_all([deck, card])
        db_session.commit()

        db_session.add(DeckCardRow(deck_id=deck.id, card_id=card.id))
        db_session.commit()

        db_session.add(DeckCardRow(deck_id=deck.id, card_id=card.id))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestSimulationRunRow:
    def test_insert_run(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        db_session.add(deck)
        db_session.commit()

        run = SimulationRunRow(
            job_id="abc123",
            deck_id=deck.id,
            turns=10,
            sims=1000,
            min_lands=36,
            max_lands=39,
            mulligan_strategy="default",
        )
        db_session.add(run)
        db_session.commit()
        assert run.id is not None
        assert run.created_at is not None

    def test_unique_job_id(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        db_session.add(deck)
        db_session.commit()

        db_session.add(SimulationRunRow(
            job_id="abc123", deck_id=deck.id, turns=10, sims=1000,
            min_lands=36, max_lands=39, mulligan_strategy="default",
        ))
        db_session.commit()

        db_session.add(SimulationRunRow(
            job_id="abc123", deck_id=deck.id, turns=10, sims=1000,
            min_lands=36, max_lands=39, mulligan_strategy="default",
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestSimulationResultRow:
    def test_unique_run_land(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        db_session.add(deck)
        db_session.commit()

        run = SimulationRunRow(
            job_id="abc123", deck_id=deck.id, turns=10, sims=1000,
            min_lands=36, max_lands=39, mulligan_strategy="default",
        )
        db_session.add(run)
        db_session.commit()

        db_session.add(SimulationResultRow(
            run_id=run.id, land_count=37,
            mean_mana=7.5, mean_draws=3.0, mean_bad_turns=1.0,
            mean_lands=3.5, mean_mulls=0.2,
            ci_mean_mana_low=7.0, ci_mean_mana_high=8.0,
            consistency=0.85, ci_consistency_low=0.80, ci_consistency_high=0.90,
            percentile_25=6.0, percentile_50=7.5, percentile_75=9.0,
        ))
        db_session.commit()

        db_session.add(SimulationResultRow(
            run_id=run.id, land_count=37,
            mean_mana=7.5, mean_draws=3.0, mean_bad_turns=1.0,
            mean_lands=3.5, mean_mulls=0.2,
            ci_mean_mana_low=7.0, ci_mean_mana_high=8.0,
            consistency=0.85, ci_consistency_low=0.80, ci_consistency_high=0.90,
            percentile_25=6.0, percentile_50=7.5, percentile_75=9.0,
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestCardPerformanceRow:
    def test_unique_run_card(self, db_session: Session):
        deck = DeckRow(name="test-deck")
        card = CardRow(name="Sol Ring")
        db_session.add_all([deck, card])
        db_session.commit()

        run = SimulationRunRow(
            job_id="abc123", deck_id=deck.id, turns=10, sims=1000,
            min_lands=36, max_lands=39, mulligan_strategy="default",
        )
        db_session.add(run)
        db_session.commit()

        db_session.add(CardPerformanceRow(
            run_id=run.id, card_id=card.id,
            top_rate=0.3, low_rate=0.1, score=0.2, rank=1,
        ))
        db_session.commit()

        db_session.add(CardPerformanceRow(
            run_id=run.id, card_id=card.id,
            top_rate=0.3, low_rate=0.1, score=0.2, rank=1,
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()
