"""Tests for the Flask web application."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from auto_goldfish.web import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _write_json(path, data):
    """Helper to write JSON to a file (used for monkeypatching save_overrides)."""
    with open(path, "w") as f:
        json.dump(data, f)
    return path


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
            "auto_goldfish.web.routes.dashboard.os.path.dirname",
            lambda *a, **kw: str(tmp_path),
        )
        response = client.get("/")
        assert b"Import" in response.data


class TestImportPage:
    def test_import_form_renders(self, client):
        response = client.get("/decks/import")
        assert response.status_code == 200
        assert b"Archidekt" in response.data

    def test_import_empty_fields_uses_defaults(self, client, monkeypatch):
        """Empty fields should fall back to the default deck URL/name."""
        captured = {}

        def fake_fetch(url, name):
            captured["url"] = url
            captured["name"] = name

        monkeypatch.setattr("auto_goldfish.web.routes.decks.fetch_and_save", fake_fetch)
        response = client.post("/decks/import", data={})
        assert captured["url"] == "https://archidekt.com/decks/81320/the_rr_connection"
        assert captured["name"] == "the_rr_connection"

    def test_import_empty_name_extracts_from_url(self, client, monkeypatch):
        """Empty deck name should be extracted from the URL."""
        captured = {}

        def fake_fetch(url, name):
            captured["url"] = url
            captured["name"] = name

        monkeypatch.setattr("auto_goldfish.web.routes.decks.fetch_and_save", fake_fetch)
        response = client.post(
            "/decks/import",
            data={"deck_url": "https://archidekt.com/decks/555/my_cool_deck"},
        )
        assert captured["url"] == "https://archidekt.com/decks/555/my_cool_deck"
        assert captured["name"] == "my_cool_deck"

    def test_import_provided_fields_override_defaults(self, client, monkeypatch):
        """Provided fields should be used instead of defaults."""
        captured = {}

        def fake_fetch(url, name):
            captured["url"] = url
            captured["name"] = name

        monkeypatch.setattr("auto_goldfish.web.routes.decks.fetch_and_save", fake_fetch)
        response = client.post(
            "/decks/import",
            data={
                "deck_url": "https://archidekt.com/decks/999/custom",
                "deck_name": "custom",
            },
        )
        assert captured["url"] == "https://archidekt.com/decks/999/custom"
        assert captured["name"] == "custom"


class TestDeckView:
    def test_view_nonexistent_deck_returns_404(self, client):
        response = client.get("/decks/nonexistent_deck_xyz")
        assert response.status_code == 404

    def test_view_existing_deck(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.load_decklist",
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
            "auto_goldfish.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.load_decklist",
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
            "auto_goldfish.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert b"Simulate" in response.data

    def test_deck_view_shows_commander(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.decks.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/decks/testdeck")
        assert b"Vren" in response.data
        assert b"Commander" in response.data


class TestSimulationRoutes:
    def _mock_deck(self, monkeypatch, tmp_path):
        """Set up deck path and decklist mocks for simulation routes."""
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )

    def test_config_form_renders(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"Simulate" in response.data
        assert b"testdeck" in response.data

    def test_config_passes_land_count(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        # Test deck has 1 Island => land_count=1
        # The hint "(deck has 1 lands..." should be present
        assert b"deck has 1 lands" in response.data

    def test_config_nonexistent_deck_404(self, client):
        response = client.get("/sim/nonexistent_xyz")
        assert response.status_code == 404

    def test_run_starts_job(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        # Mock the runner to avoid actually running a sim
        from auto_goldfish.web.routes import simulation as sim_mod

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
        from auto_goldfish.web.routes import simulation as sim_mod

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

    def test_status_completed_returns_inline_results(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: {
                "job_id": jid,
                "deck_name": "test",
                "status": "completed",
                "progress": 2,
                "total": 2,
                "config": {},
                "results": _make_mock_results(),
                "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/status/abc123")
        assert response.status_code == 200
        # Should NOT redirect — results are rendered inline
        assert "HX-Redirect" not in response.headers
        # Should contain results content
        assert b"results-content" in response.data
        assert b"Summary Statistics" in response.data

    def test_status_unknown_job_404(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "get_status": lambda self, jid: None,
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        response = client.get("/sim/status/nonexistent")
        assert response.status_code == 404

    def test_api_results_json(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

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


class TestSimulationValidation:
    """Tests for web UI compute-limit validation."""

    def _post_sim(self, client, monkeypatch, tmp_path, **overrides):
        """POST to /sim/testdeck/run with default valid params, applying overrides."""
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

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

        data = {
            "turns": "10",
            "sims": "1000",
            "min_lands": "34",
            "max_lands": "38",
        }
        data.update(overrides)
        return client.post("/sim/testdeck/run", data=data)

    def test_valid_params_accepted(self, client, tmp_path, monkeypatch):
        response = self._post_sim(client, monkeypatch, tmp_path)
        assert response.status_code == 200

    def test_sims_over_limit_returns_400(self, client, tmp_path, monkeypatch):
        response = self._post_sim(client, monkeypatch, tmp_path, sims="20000")
        assert response.status_code == 400
        assert b"10000" in response.data

    def test_turns_over_limit_returns_400(self, client, tmp_path, monkeypatch):
        response = self._post_sim(client, monkeypatch, tmp_path, turns="20")
        assert response.status_code == 400
        assert b"14" in response.data

    def test_land_sweep_over_limit_returns_400(self, client, tmp_path, monkeypatch):
        response = self._post_sim(
            client, monkeypatch, tmp_path, min_lands="20", max_lands="35",
        )
        assert response.status_code == 400
        assert b"10" in response.data

    def test_min_lands_greater_than_max_returns_400(self, client, tmp_path, monkeypatch):
        response = self._post_sim(
            client, monkeypatch, tmp_path, min_lands="40", max_lands="35",
        )
        assert response.status_code == 400
        assert b"less than or equal" in response.data

    def test_sims_at_limit_accepted(self, client, tmp_path, monkeypatch):
        response = self._post_sim(client, monkeypatch, tmp_path, sims="2000")
        assert response.status_code == 200

    def test_turns_at_limit_accepted(self, client, tmp_path, monkeypatch):
        response = self._post_sim(client, monkeypatch, tmp_path, turns="14")
        assert response.status_code == 200

    def test_land_sweep_at_limit_accepted(self, client, tmp_path, monkeypatch):
        response = self._post_sim(
            client, monkeypatch, tmp_path, min_lands="30", max_lands="40",
        )
        assert response.status_code == 200


def _make_card_performance():
    return {
        "high_performing": [
            {"name": "Creature 0", "cost": "{1}", "cmc": 1, "effects": "",
             "top_rate": 0.8, "low_rate": 0.2, "score": 0.6},
            {"name": "Creature 1", "cost": "{2}", "cmc": 2, "effects": "",
             "top_rate": 0.7, "low_rate": 0.3, "score": 0.4},
        ],
        "low_performing": [
            {"name": "Creature 5", "cost": "{6}", "cmc": 6, "effects": "",
             "top_rate": 0.1, "low_rate": 0.5, "score": -0.4},
            {"name": "Creature 4", "cost": "{5}", "cmc": 5, "effects": "",
             "top_rate": 0.2, "low_rate": 0.4, "score": -0.2},
        ],
        "total_top_games": 100,
        "total_low_games": 100,
    }


def _make_replay_data():
    turn = {
        "turn": 1,
        "hand_before_draw": ["Island 0", "Creature 1"],
        "played": [
            {"name": "Island 0", "cost": "", "mana_spent": 0, "is_land": True},
            {"name": "Creature 1", "cost": "{1}", "mana_spent": 1, "is_land": False},
        ],
        "mana_spent_this_turn": 1,
        "total_mana_production": 1,
        "hand_after": ["Creature 2"],
        "battlefield": [],
        "lands": ["Island 0"],
        "graveyard": [],
    }
    game = {
        "total_mana": 15,
        "mulligans": 0,
        "starting_hand": ["Island 0", "Creature 1", "Creature 2"],
        "turns": [turn],
    }
    return {
        "top": [game],
        "mid": [game],
        "low": [game],
    }


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
            "card_performance": _make_card_performance(),
            "replay_data": _make_replay_data(),
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
            "card_performance": _make_card_performance(),
            "replay_data": _make_replay_data(),
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
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert response.status_code == 200
        assert b"Results" in response.data

    def test_results_page_shows_stats_table(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"10.50" in response.data  # mean_mana formatted
        assert b"0.850" in response.data  # consistency
        assert b"36" in response.data  # land count

    def test_results_page_shows_distribution_table(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Distribution" in response.data
        assert b"Top 1%" in response.data

    def test_results_page_has_metric_definitions(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Metric Definitions" in response.data

    def test_results_page_has_card_performance(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Card Performance" in response.data
        assert b"Top Performers" in response.data
        assert b"Low Performers" in response.data

    def test_results_page_has_chart_canvases(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"manaChart" in response.data
        assert b"distributionChart" in response.data
        assert b"consistencyChart" in response.data

    def test_results_page_has_game_replays(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Game Replays" in response.data

    def test_results_page_has_quantile_tabs(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(_make_mock_results()))
        response = client.get("/sim/results/abc123")
        assert b"Top Quartile" in response.data
        assert b"Mid" in response.data
        assert b"Low Quartile" in response.data

    def test_results_incomplete_job_404(self, client, monkeypatch):
        from auto_goldfish.web.routes import simulation as sim_mod

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
        from auto_goldfish.web.routes import simulation as sim_mod

        results_data = _make_mock_results()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: self._mock_runner(results_data))
        response = client.get("/sim/api/results/abc123")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert all("mean_mana" in d for d in data)
        assert all("distribution_stats" in d for d in data)
        assert all("consistency" in d for d in data)


class TestEffectOverrides:
    def test_config_page_includes_card_effects(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"EFFECT_SCHEMA" in response.data
        assert b"CARD_EFFECTS" in response.data
        assert b"Sol Ring" in response.data

    def test_config_page_shows_effects_section(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        response = client.get("/sim/testdeck")
        assert b"Card Effects" in response.data

    def test_run_with_overrides_passes_to_config(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

        submitted_configs = []

        class CapturingRunner:
            def submit(self, name, cfg):
                submitted_configs.append(cfg)
                return "abc123"

            def get_status(self, jid):
                return {
                    "job_id": "abc123",
                    "deck_name": "testdeck",
                    "status": "running",
                    "progress": 0,
                    "total": 4,
                    "config": {},
                    "results": [],
                    "error": None,
                }

        monkeypatch.setattr(sim_mod, "get_runner", lambda: CapturingRunner())

        overrides = {"Sol Ring": {"effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 5}}], "ramp": True}}
        response = client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
            "effect_overrides": json.dumps(overrides),
        })
        assert response.status_code == 200
        assert len(submitted_configs) == 1
        assert submitted_configs[0]["effect_overrides"] == overrides

    def test_run_with_invalid_json_overrides_uses_empty(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

        submitted_configs = []

        class CapturingRunner:
            def submit(self, name, cfg):
                submitted_configs.append(cfg)
                return "abc123"

            def get_status(self, jid):
                return {
                    "job_id": "abc123",
                    "deck_name": "testdeck",
                    "status": "running",
                    "progress": 0,
                    "total": 4,
                    "config": {},
                    "results": [],
                    "error": None,
                }

        monkeypatch.setattr(sim_mod, "get_runner", lambda: CapturingRunner())

        response = client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
            "effect_overrides": "{invalid json",
        })
        assert response.status_code == 200
        assert submitted_configs[0]["effect_overrides"] == {}

    def test_run_without_overrides_has_empty_dict(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

        submitted_configs = []

        class CapturingRunner:
            def submit(self, name, cfg):
                submitted_configs.append(cfg)
                return "abc123"

            def get_status(self, jid):
                return {
                    "job_id": "abc123",
                    "deck_name": "testdeck",
                    "status": "running",
                    "progress": 0,
                    "total": 4,
                    "config": {},
                    "results": [],
                    "error": None,
                }

        monkeypatch.setattr(sim_mod, "get_runner", lambda: CapturingRunner())

        response = client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
        })
        assert response.status_code == 200
        assert submitted_configs[0]["effect_overrides"] == {}

    def test_run_saves_overrides_to_disk(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        overrides_file = str(tmp_path / "testdeck.overrides.json")
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.save_overrides",
            lambda name, data: _write_json(overrides_file, data),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "submit": lambda self, name, cfg: "abc123",
            "get_status": lambda self, jid: {
                "job_id": "abc123", "deck_name": "testdeck",
                "status": "running", "progress": 0, "total": 4,
                "config": {}, "results": [], "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        overrides = {"Sol Ring": {"effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 5}}]}}
        client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
            "effect_overrides": json.dumps(overrides),
        })
        with open(overrides_file) as f:
            saved = json.load(f)
        assert saved == overrides

    def test_config_loads_saved_overrides(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_decklist",
            lambda name: json.loads(
                open(os.path.join(root, "decks", name, f"{name}.json")).read()
            ),
        )
        saved = {"Sol Ring": {"effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 5}}]}}
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: saved,
        )
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"SAVED_OVERRIDES" in response.data

    def test_empty_overrides_clears_file(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        overrides_file = str(tmp_path / "testdeck.overrides.json")
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.save_overrides",
            lambda name, data: _write_json(overrides_file, data),
        )
        from auto_goldfish.web.routes import simulation as sim_mod

        mock_runner = type("MockRunner", (), {
            "submit": lambda self, name, cfg: "abc123",
            "get_status": lambda self, jid: {
                "job_id": "abc123", "deck_name": "testdeck",
                "status": "running", "progress": 0, "total": 4,
                "config": {}, "results": [], "error": None,
            },
        })()
        monkeypatch.setattr(sim_mod, "get_runner", lambda: mock_runner)

        client.post("/sim/testdeck/run", data={
            "turns": "10", "sims": "100", "min_lands": "36", "max_lands": "39",
            "effect_overrides": "{}",
        })
        with open(overrides_file) as f:
            saved = json.load(f)
        assert saved == {}

    def test_overrides_api_saves_to_disk(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        overrides_file = str(tmp_path / "testdeck.overrides.json")
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.save_overrides",
            lambda name, data: _write_json(overrides_file, data),
        )
        overrides = {"Sol Ring": {"effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 3}}]}}
        response = client.post(
            "/sim/testdeck/overrides",
            data=json.dumps(overrides),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}
        with open(overrides_file) as f:
            saved = json.load(f)
        assert saved == overrides

    def test_overrides_api_clears_with_empty(self, client, tmp_path, monkeypatch):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        overrides_file = str(tmp_path / "testdeck.overrides.json")
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.save_overrides",
            lambda name, data: _write_json(overrides_file, data),
        )
        response = client.post(
            "/sim/testdeck/overrides",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 200
        with open(overrides_file) as f:
            saved = json.load(f)
        assert saved == {}

    def test_overrides_api_nonexistent_deck_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: str(tmp_path / "nonexistent" / "nonexistent.json"),
        )
        response = client.post(
            "/sim/nonexistent/overrides",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 404
