"""Tests for card annotation persistence."""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from auto_goldfish.db.models import Base, CardAnnotationRow
from auto_goldfish.db.persistence import get_annotation_stats, save_card_annotation


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestSaveCardAnnotation:
    def test_creates_annotation(self, db_session: Session):
        row = save_card_annotation(db_session, "Sol Ring", '{"categories": []}', "human")
        db_session.commit()
        assert row.id is not None
        assert row.card_name == "Sol Ring"
        assert row.source == "human"

    def test_multiple_annotations_per_card(self, db_session: Session):
        save_card_annotation(db_session, "Sol Ring", '{"categories": [{"category": "ramp"}]}', "human")
        save_card_annotation(db_session, "Sol Ring", '{"categories": []}', "human")
        db_session.commit()

        rows = db_session.execute(select(CardAnnotationRow)).scalars().all()
        assert len(rows) == 2

    def test_default_source(self, db_session: Session):
        row = save_card_annotation(db_session, "Sol Ring", '{}')
        db_session.commit()
        assert row.source == "human"

    def test_ai_source(self, db_session: Session):
        row = save_card_annotation(db_session, "Sol Ring", '{}', "ai")
        db_session.commit()
        assert row.source == "ai"


class TestGetAnnotationStats:
    def test_empty_cards(self, db_session: Session):
        result = get_annotation_stats(db_session, [])
        assert result == {}

    def test_no_annotations(self, db_session: Session):
        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 0
        assert result["Sol Ring"]["has_human"] is False
        assert result["Sol Ring"]["is_controversial"] is False
        assert result["Sol Ring"]["latest_effects_json"] is None

    def test_single_human_annotation(self, db_session: Session):
        effects = json.dumps({"categories": [{"category": "ramp"}]})
        save_card_annotation(db_session, "Sol Ring", effects, "human")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 1
        assert result["Sol Ring"]["has_human"] is True
        assert result["Sol Ring"]["is_controversial"] is False
        assert result["Sol Ring"]["latest_effects_json"] == effects

    def test_consistent_annotations_not_controversial(self, db_session: Session):
        effects = json.dumps({"categories": [{"category": "ramp"}]})
        save_card_annotation(db_session, "Sol Ring", effects, "human")
        save_card_annotation(db_session, "Sol Ring", effects, "human")
        save_card_annotation(db_session, "Sol Ring", effects, "human")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 3
        assert result["Sol Ring"]["is_controversial"] is False

    def test_controversial_annotations(self, db_session: Session):
        effects_a = json.dumps({"categories": [{"category": "ramp"}]})
        effects_b = json.dumps({"categories": [{"category": "draw"}]})
        save_card_annotation(db_session, "Sol Ring", effects_a, "human")
        save_card_annotation(db_session, "Sol Ring", effects_b, "human")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 2
        assert result["Sol Ring"]["is_controversial"] is True

    def test_majority_not_controversial(self, db_session: Session):
        effects_a = json.dumps({"categories": [{"category": "ramp"}]})
        effects_b = json.dumps({"categories": [{"category": "draw"}]})
        save_card_annotation(db_session, "Sol Ring", effects_a, "human")
        save_card_annotation(db_session, "Sol Ring", effects_a, "human")
        save_card_annotation(db_session, "Sol Ring", effects_b, "human")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 3
        # 2/3 > 50%, so not controversial
        assert result["Sol Ring"]["is_controversial"] is False

    def test_ai_annotations_not_counted_as_human(self, db_session: Session):
        save_card_annotation(db_session, "Sol Ring", '{}', "ai")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring"])
        assert result["Sol Ring"]["human_count"] == 0
        assert result["Sol Ring"]["has_human"] is False
        # But latest should still be present
        assert result["Sol Ring"]["latest_effects_json"] == '{}'
        assert result["Sol Ring"]["latest_source"] == "ai"

    def test_multiple_cards(self, db_session: Session):
        save_card_annotation(db_session, "Sol Ring", '{"a":1}', "human")
        save_card_annotation(db_session, "Rhystic Study", '{"b":2}', "human")
        db_session.commit()

        result = get_annotation_stats(db_session, ["Sol Ring", "Rhystic Study", "Unknown"])
        assert "Sol Ring" in result
        assert "Rhystic Study" in result
        assert "Unknown" in result
        assert result["Sol Ring"]["has_human"] is True
        assert result["Rhystic Study"]["has_human"] is True
        assert result["Unknown"]["has_human"] is False
