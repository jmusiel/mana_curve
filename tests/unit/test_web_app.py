"""Tests for the Flask web application."""

import json
import os
from unittest.mock import patch

import pytest

from mana_curve.web import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _create_test_deck(tmp_path, name="testdeck"):
    """Create a minimal deck JSON in tmp_path and return the path."""
    deck_dir = tmp_path / "decks" / name
    deck_dir.mkdir(parents=True)
    deck_file = deck_dir / f"{name}.json"
    cards = [
        {
            "name": "Island",
            "quantity": 1,
            "oracle_cmc": 0,
            "cmc": 0,
            "cost": "",
            "text": "",
            "types": ["Land"],
            "sub_types": ["Island"],
            "super_types": ["Basic"],
            "identity": ["Blue"],
            "user_category": "Land",
            "commander": False,
        },
        {
            "name": "Sol Ring",
            "quantity": 1,
            "oracle_cmc": 1,
            "cmc": 1,
            "cost": "{1}",
            "text": "{T}: Add {C}{C}.",
            "types": ["Artifact"],
            "sub_types": [],
            "super_types": [],
            "identity": [],
            "user_category": "Ramp",
            "commander": False,
        },
        {
            "name": "Vren, the Relentless",
            "quantity": 1,
            "oracle_cmc": 2,
            "cmc": 2,
            "cost": "{U}{B}",
            "text": "Commander text",
            "types": ["Creature"],
            "sub_types": ["Rat"],
            "super_types": ["Legendary"],
            "identity": ["Blue", "Black"],
            "user_category": "Commander",
            "commander": True,
        },
    ]
    deck_file.write_text(json.dumps(cards))
    return str(tmp_path)


class TestCreateApp:
    def test_create_app_returns_flask_instance(self, app):
        from flask import Flask

        assert isinstance(app, Flask)

    def test_app_has_secret_key(self, app):
        assert app.config["SECRET_KEY"]


class TestDashboard:
    def test_dashboard_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_dashboard_contains_title(self, client):
        response = client.get("/")
        assert b"Saved Decks" in response.data

    def test_dashboard_shows_import_link_when_empty(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mana_curve.web.routes.dashboard.os.path.dirname",
            lambda *a, **kw: str(tmp_path),
        )
        response = client.get("/")
        assert b"Import" in response.data


class TestImportPage:
    def test_import_form_renders(self, client):
        response = client.get("/decks/import")
        assert response.status_code == 200
        assert b"Archidekt" in response.data

    def test_import_missing_fields_returns_400(self, client):
        response = client.post("/decks/import", data={})
        assert response.status_code == 400

    def test_import_missing_deck_name_returns_400(self, client):
        response = client.post(
            "/decks/import",
            data={"deck_url": "https://archidekt.com/decks/123/test"},
        )
        assert response.status_code == 400

    def test_import_missing_deck_url_returns_400(self, client):
        response = client.post(
            "/decks/import",
            data={"deck_name": "test"},
        )
        assert response.status_code == 400


class TestDeckView:
    def test_view_nonexistent_deck_returns_404(self, client):
        response = client.get("/decks/nonexistent_deck_xyz")
        assert response.status_code == 404

    def test_view_existing_deck(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert response.status_code == 200
        assert b"testdeck" in response.data

    def test_deck_view_groups_cards(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert response.status_code == 200
        assert b"card-group" in response.data
        assert b"Land" in response.data
        assert b"Ramp" in response.data

    def test_deck_view_shows_simulate_link(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert b"Simulate" in response.data

    def test_deck_view_shows_commander(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "mana_curve.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert b"Vren" in response.data
        assert b"Commander" in response.data


class TestSimulationRoutes:
    def test_config_form_renders(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"Simulate" in response.data
        assert b"testdeck" in response.data

    def test_config_nonexistent_deck_404(self, client):
        response = client.get("/sim/nonexistent_xyz")
        assert response.status_code == 404

    def test_run_starts_job(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "mana_curve.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        # Mock the runner to avoid actually running a sim
        from mana_curve.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "submit": lambda self, name, cfg: "abc123",
            "get_status": lambda self, jid: {
                "job_id": "abc123",
                "deck_name": "testdeck",
                "status": "running",
                "progress": 0,
                "total": 4,
                "config": {},
                "results": [],
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
        })
        assert response.status_code == 200
        assert b"running" in response.data or b"pending" in response.data

    def test_status_polling(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "running",
                "progress": 2,
                "total": 4,
                "config": {},
                "results": [],
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/status/abc123")
        assert response.status_code == 200
        assert b"2" in response.data

    def test_status_completed_redirects(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "completed",
                "progress": 4,
                "total": 4,
                "config": {},
                "results": [{"land_count": 36}],
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/status/abc123")
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/sim/results/abc123"

    def test_status_unknown_job_404(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: None,
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/status/nonexistent")
        assert response.status_code == 404

    def test_api_results_json(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        results_data = [
            {"land_count": 36, "mean_mana": 10.5},
            {"land_count": 37, "mean_mana": 11.2},
        ]
        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "completed",
                "progress": 2,
                "total": 2,
                "config": {},
                "results": results_data,
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/api/results/abc123")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert data[0]["land_count"] == 36


def _make_mock_results():
    return [
        {
            "land_count": 36,
            "mean_mana": 10.5,
            "consistency": 0.85,
            "mean_bad_turns": 1.2,
            "mean_mid_turns": 2.3,
            "mean_lands": 5.1,
            "mean_mulls": 0.3,
            "mean_draws": 10.0,
            "percentile_25": 7.0,
            "percentile_50": 10.0,
            "percentile_75": 14.0,
            "threshold_percent": 0.2,
            "threshold_mana": 5.0,
            "distribution_stats": {
                "top_centile": 0.01,
                "top_decile": 0.10,
                "top_quartile": 0.25,
                "top_half": 0.50,
                "low_half": 0.50,
                "low_quartile": 0.25,
                "low_decile": 0.10,
                "low_centile": 0.01,
            },
        },
        {
            "land_count": 37,
            "mean_mana": 11.2,
            "consistency": 0.88,
            "mean_bad_turns": 1.0,
            "mean_mid_turns": 2.0,
            "mean_lands": 5.5,
            "mean_mulls": 0.2,
            "mean_draws": 10.0,
            "percentile_25": 8.0,
            "percentile_50": 11.0,
            "percentile_75": 15.0,
            "threshold_percent": 0.18,
            "threshold_mana": 6.0,
            "distribution_stats": {
                "top_centile": 0.01,
                "top_decile": 0.11,
                "top_quartile": 0.26,
                "top_half": 0.51,
                "low_half": 0.49,
                "low_quartile": 0.24,
                "low_decile": 0.09,
                "low_centile": 0.01,
            },
        },
    ]


class TestResultsPage:
    def _mock_runner(self, results_data):
        return type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "completed",
                "progress": len(results_data),
                "total": len(results_data),
                "config": {},
                "results": results_data,
                "error": None,
            },
        })()

    def test_results_page_renders(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert response.status_code == 200
        assert b"Results" in response.data

    def test_results_page_shows_stats_table(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"10.50" in response.data  # mean_mana formatted
        assert b"0.850" in response.data  # consistency
        assert b"36" in response.data  # land count

    def test_results_page_shows_distribution_table(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Distribution" in response.data
        assert b"Top 1%" in response.data

    def test_results_page_has_chart_canvases(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"manaChart" in response.data
        assert b"distributionChart" in response.data
        assert b"consistencyChart" in response.data

    def test_results_incomplete_job_404(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "running",
                "progress": 1,
                "total": 4,
                "config": {},
                "results": [],
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)
        response = client.get("/sim/results/abc123")
        assert response.status_code == 404

    def test_api_results_returns_valid_json(self, client, monkeypatch):
        from mana_curve.web.routes import simulation as sim_mod

        results_data = _make_mock_results()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(results_data))
        response = client.get("/sim/api/results/abc123")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert all("mean_mana" in d for d in data)
        assert all("distribution_stats" in d for d in data)
        assert all("consistency" in d for d in data)
