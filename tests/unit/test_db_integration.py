"""Integration tests -- verify web layer calls DB persistence and failures don't crash."""

from unittest.mock import MagicMock, patch

import pytest

from auto_goldfish.web.services.simulation_runner import SimJob


class TestSimulationRunnerPersistence:
    """Verify _run_simulation calls persist_completed_job on success."""

    @patch("auto_goldfish.web.services.simulation_runner.load_decklist")
    @patch("auto_goldfish.web.services.simulation_runner.Goldfisher")
    @patch("auto_goldfish.db.persistence.persist_completed_job")
    def test_persist_called_on_completion(self, mock_persist, mock_goldfisher_cls, mock_load):
        from auto_goldfish.web.services.simulation_runner import SimulationRunner

        mock_load.return_value = []
        mock_result = MagicMock()
        mock_goldfisher = MagicMock()
        mock_goldfisher.simulate.return_value = mock_result
        mock_goldfisher.land_count = 37
        mock_goldfisher_cls.return_value = mock_goldfisher

        # Mock result_to_dict
        with patch("auto_goldfish.web.services.simulation_runner.result_to_dict", return_value={"land_count": 37}):
            runner = SimulationRunner()
            job = SimJob(
                job_id="test123",
                deck_name="test-deck",
                config={"turns": 10, "sims": 100, "min_lands": 37, "max_lands": 37},
                total=1,
            )
            runner._run_simulation(job)

        assert job.status == "completed"
        mock_persist.assert_called_once_with(job)

    @patch("auto_goldfish.web.services.simulation_runner.load_decklist")
    @patch("auto_goldfish.web.services.simulation_runner.Goldfisher")
    @patch("auto_goldfish.db.persistence.persist_completed_job", side_effect=Exception("DB error"))
    def test_persist_failure_does_not_crash(self, mock_persist, mock_goldfisher_cls, mock_load):
        from auto_goldfish.web.services.simulation_runner import SimulationRunner

        mock_load.return_value = []
        mock_result = MagicMock()
        mock_goldfisher = MagicMock()
        mock_goldfisher.simulate.return_value = mock_result
        mock_goldfisher.land_count = 37
        mock_goldfisher_cls.return_value = mock_goldfisher

        with patch("auto_goldfish.web.services.simulation_runner.result_to_dict", return_value={"land_count": 37}):
            runner = SimulationRunner()
            job = SimJob(
                job_id="test456",
                deck_name="test-deck",
                config={"turns": 10, "sims": 100, "min_lands": 37, "max_lands": 37},
                total=1,
            )
            # Should not raise
            runner._run_simulation(job)

        assert job.status == "completed"

    @patch("auto_goldfish.web.services.simulation_runner.load_decklist", side_effect=Exception("Deck not found"))
    def test_sim_failure_does_not_persist(self, mock_load):
        from auto_goldfish.web.services.simulation_runner import SimulationRunner

        with patch("auto_goldfish.db.persistence.persist_completed_job") as mock_persist:
            runner = SimulationRunner()
            job = SimJob(
                job_id="test789",
                deck_name="nonexistent",
                config={"turns": 10, "sims": 100, "min_lands": 37, "max_lands": 37},
                total=1,
            )
            runner._run_simulation(job)

        assert job.status == "failed"
        mock_persist.assert_not_called()


class TestConfigRoutePersistence:
    """Verify config route calls persist_deck_cards and failures don't crash."""

    @pytest.fixture
    def app(self, tmp_path):
        import json
        import os

        from auto_goldfish.web import create_app

        # Create a minimal deck file
        decks_dir = tmp_path / "decks"
        decks_dir.mkdir()
        deck_file = decks_dir / "test-deck.json"
        deck_data = [
            {"name": "Sol Ring", "cmc": 1, "types": ["artifact"], "quantity": 1},
            {"name": "Island", "cmc": 0, "types": ["land"], "quantity": 37},
        ]
        deck_file.write_text(json.dumps(deck_data))

        os.environ.pop("DATABASE_URL", None)
        app = create_app()
        app.config["TESTING"] = True

        with patch("auto_goldfish.web.routes.simulation.get_deckpath", return_value=str(deck_file)):
            with patch("auto_goldfish.web.routes.simulation.load_decklist", return_value=deck_data):
                with patch("auto_goldfish.web.routes.simulation.load_overrides", return_value={}):
                    yield app

    @patch("auto_goldfish.db.persistence.persist_deck_cards")
    def test_config_calls_persist(self, mock_persist, app):
        with app.test_client() as client:
            with patch("auto_goldfish.web.routes.simulation.get_deckpath", return_value="/tmp/exists"):
                with patch("os.path.isfile", return_value=True):
                    with patch("auto_goldfish.web.routes.simulation.load_decklist", return_value=[
                        {"name": "Sol Ring", "cmc": 1, "types": ["artifact"], "quantity": 1},
                        {"name": "Island", "cmc": 0, "types": ["land"], "quantity": 37},
                    ]):
                        with patch("auto_goldfish.web.routes.simulation.load_overrides", return_value={}):
                            resp = client.get("/sim/test-deck")

        assert resp.status_code == 200
        mock_persist.assert_called_once()
        args = mock_persist.call_args
        assert args[0][0] == "test-deck"  # deck_name

    @patch("auto_goldfish.db.persistence.persist_deck_cards", side_effect=Exception("DB error"))
    def test_config_persist_failure_does_not_crash(self, mock_persist, app):
        with app.test_client() as client:
            with patch("auto_goldfish.web.routes.simulation.get_deckpath", return_value="/tmp/exists"):
                with patch("os.path.isfile", return_value=True):
                    with patch("auto_goldfish.web.routes.simulation.load_decklist", return_value=[
                        {"name": "Sol Ring", "cmc": 1, "types": ["artifact"], "quantity": 1},
                        {"name": "Island", "cmc": 0, "types": ["land"], "quantity": 37},
                    ]):
                        with patch("auto_goldfish.web.routes.simulation.load_overrides", return_value={}):
                            resp = client.get("/sim/test-deck")

        # Should still return 200 despite DB failure
        assert resp.status_code == 200


class TestAppFactoryDB:
    """Verify create_app conditionally initializes DB."""

    @patch("auto_goldfish.db.session.init_db")
    def test_init_db_called_when_url_set(self, mock_init):
        import os

        from auto_goldfish.web import create_app

        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        try:
            create_app()
            mock_init.assert_called_once_with("sqlite:///:memory:")
        finally:
            os.environ.pop("DATABASE_URL", None)

    @patch("auto_goldfish.db.session.init_db")
    def test_init_db_not_called_when_url_empty(self, mock_init):
        import os

        from auto_goldfish.web import create_app

        os.environ.pop("DATABASE_URL", None)
        create_app()
        mock_init.assert_not_called()
