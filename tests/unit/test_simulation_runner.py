"""Tests for the background SimulationRunner."""

import time
from unittest.mock import MagicMock, patch

import pytest

from mana_curve.web.services.simulation_runner import SimJob, SimulationRunner


@pytest.fixture
def runner():
    return SimulationRunner()


class TestSimJob:
    def test_default_status(self):
        job = SimJob(job_id="abc", deck_name="test", config={})
        assert job.status == "pending"
        assert job.progress == 0
        assert job.results == []
        assert job.error is None


class TestSimulationRunner:
    def test_get_status_unknown_job(self, runner):
        assert runner.get_status("nonexistent") is None

    def test_submit_returns_job_id(self, runner):
        with patch.object(runner, "_run_simulation"):
            job_id = runner.submit("test", {"min_lands": 36, "max_lands": 36})
            assert isinstance(job_id, str)
            assert len(job_id) == 12

    def test_submit_creates_job(self, runner):
        with patch.object(runner, "_run_simulation"):
            job_id = runner.submit("test", {"min_lands": 36, "max_lands": 37})
            status = runner.get_status(job_id)
            assert status is not None
            assert status["deck_name"] == "test"
            assert status["total"] == 2

    @patch("mana_curve.web.services.simulation_runner.load_decklist")
    @patch("mana_curve.web.services.simulation_runner.Goldfisher")
    @patch("mana_curve.web.services.simulation_runner.result_to_dict")
    def test_successful_completion(self, mock_to_dict, mock_goldfisher_cls, mock_load):
        runner = SimulationRunner()

        mock_load.return_value = [{"name": "Island", "types": ["Land"]}]

        mock_result = MagicMock()
        mock_goldfisher = MagicMock()
        mock_goldfisher.land_count = 36
        mock_goldfisher.simulate.return_value = mock_result
        mock_goldfisher_cls.return_value = mock_goldfisher
        mock_to_dict.return_value = {"land_count": 36, "mean_mana": 10.0}

        job_id = runner.submit("test", {"min_lands": 36, "max_lands": 36, "turns": 5, "sims": 10})

        # Wait for completion
        for _ in range(50):
            status = runner.get_status(job_id)
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        status = runner.get_status(job_id)
        assert status["status"] == "completed"
        assert len(status["results"]) == 1
        assert status["results"][0]["land_count"] == 36
        assert status["error"] is None

    @patch("mana_curve.web.services.simulation_runner.load_decklist")
    def test_failure_sets_error(self, mock_load):
        runner = SimulationRunner()
        mock_load.side_effect = FileNotFoundError("deck not found")

        job_id = runner.submit("missing", {"min_lands": 36, "max_lands": 36})

        for _ in range(50):
            status = runner.get_status(job_id)
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        status = runner.get_status(job_id)
        assert status["status"] == "failed"
        assert "deck not found" in status["error"]

    @patch("mana_curve.web.services.simulation_runner.load_decklist")
    @patch("mana_curve.web.services.simulation_runner.Goldfisher")
    @patch("mana_curve.web.services.simulation_runner.result_to_dict")
    def test_progress_tracking(self, mock_to_dict, mock_goldfisher_cls, mock_load):
        runner = SimulationRunner()
        mock_load.return_value = [{"name": "Island", "types": ["Land"]}]

        mock_result = MagicMock()
        mock_goldfisher = MagicMock()
        mock_goldfisher.land_count = 36
        mock_goldfisher.simulate.return_value = mock_result
        mock_goldfisher_cls.return_value = mock_goldfisher
        mock_to_dict.return_value = {"land_count": 36}

        job_id = runner.submit("test", {"min_lands": 36, "max_lands": 38, "sims": 10})

        for _ in range(50):
            status = runner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(0.05)

        status = runner.get_status(job_id)
        assert status["progress"] == 3
        assert status["total"] == 3
        assert len(status["results"]) == 3
