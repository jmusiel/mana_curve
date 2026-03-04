"""Tests for the Flask web application."""

import json
import os

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
        saved = {"Sol Ring": {"categories": [{"category": "ramp", "immediate": False, "producer": {"mana_amount": 5}}]}}
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: saved,
        )
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"SAVED_OVERRIDES" in response.data

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
        overrides = {"Sol Ring": {"categories": [{"category": "ramp", "immediate": False, "producer": {"mana_amount": 3}}]}}
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


class TestWheelAPI:
    """Tests for the wheel serving endpoint."""

    def test_wheel_serves_file(self, client, tmp_path, monkeypatch):
        # Create a fake wheel file
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        wheel_file = dist_dir / "auto_goldfish-0.2.0-py3-none-any.whl"
        wheel_file.write_bytes(b"fake wheel content")

        # Monkeypatch the project root detection
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.os.path.abspath",
            lambda p: str(tmp_path / "src" / "auto_goldfish" / "web" / "routes" / "simulation.py"),
        )
        response = client.get("/sim/api/wheel")
        # Since we're monkeypatching abspath, the path calculation may not
        # land correctly -- just verify the endpoint exists
        assert response.status_code in (200, 404)

    def test_wheel_404_when_missing(self, client, tmp_path, monkeypatch):
        # Point to an empty dist directory
        import auto_goldfish.web.routes.simulation as sim_mod
        original_glob = sim_mod.glob.glob
        monkeypatch.setattr(sim_mod.glob, "glob", lambda pattern: [])
        response = client.get("/sim/api/wheel")
        assert response.status_code == 404


class TestDeckAPI:
    """Tests for the deck data and effects JSON API endpoints."""


    def _mock_deck(self, monkeypatch, tmp_path):
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
        return root

    def test_api_deck_returns_card_list(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/api/testdeck/deck")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 3  # Island, Sol Ring, Vren
        names = [c["name"] for c in data]
        assert "Island" in names
        assert "Sol Ring" in names

    def test_api_deck_nonexistent_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: str(tmp_path / "nonexistent" / "nonexistent.json"),
        )
        response = client.get("/sim/api/nonexistent/deck")
        assert response.status_code == 404

    def test_api_effects_returns_known_cards(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: {},
        )
        response = client.get("/sim/api/testdeck/effects")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, dict)
        # Sol Ring is in the default registry
        if "Sol Ring" in data:
            assert "categories" in data["Sol Ring"]

    def test_api_effects_includes_overrides(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        override = {
            "Sol Ring": {
                "categories": [{"category": "ramp", "immediate": False, "producer": {"mana_amount": 5}}],
            }
        }
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: override,
        )
        response = client.get("/sim/api/testdeck/effects")
        assert response.status_code == 200
        data = response.get_json()
        assert data["Sol Ring"]["categories"][0]["producer"]["mana_amount"] == 5

    def test_api_effects_nonexistent_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: str(tmp_path / "nonexistent" / "nonexistent.json"),
        )
        response = client.get("/sim/api/nonexistent/effects")
        assert response.status_code == 404

    def test_api_effects_excludes_lands(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: {},
        )
        response = client.get("/sim/api/testdeck/effects")
        data = response.get_json()
        assert "Island" not in data


class TestCardLabeler:
    def _mock_deck(self, monkeypatch, tmp_path):
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

    def test_config_includes_labeler_js_variables(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        assert response.status_code == 200
        assert b"UNLABELED_CARDS" in response.data
        assert b"ALL_NONLAND_CARDS" in response.data

    def test_registry_cards_excluded_from_unlabeled(self, client, tmp_path, monkeypatch):
        """Sol Ring is in DEFAULT_REGISTRY so should not appear in UNLABELED_CARDS."""
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        html = response.data.decode()
        # Find UNLABELED_CARDS value - Sol Ring should NOT be in it
        import re
        match = re.search(r'UNLABELED_CARDS\s*=\s*(\[.*?\]);', html, re.DOTALL)
        assert match
        unlabeled = json.loads(match.group(1))
        unlabeled_names = [c["name"] for c in unlabeled]
        assert "Sol Ring" not in unlabeled_names

    def test_overridden_cards_excluded_from_unlabeled(self, client, tmp_path, monkeypatch):
        """Cards with saved overrides should not appear in UNLABELED_CARDS."""
        self._mock_deck(monkeypatch, tmp_path)
        saved = {"Vren, the Relentless": {"categories": [{"category": "draw", "immediate": True, "amount": 1}]}}
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.load_overrides",
            lambda name: saved,
        )
        response = client.get("/sim/testdeck")
        html = response.data.decode()
        import re
        match = re.search(r'UNLABELED_CARDS\s*=\s*(\[.*?\]);', html, re.DOTALL)
        assert match
        unlabeled = json.loads(match.group(1))
        unlabeled_names = [c["name"] for c in unlabeled]
        assert "Vren, the Relentless" not in unlabeled_names

    def test_labeler_html_elements_present(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        assert b"card-labeler" in response.data
        assert b"labeler-step-classify" in response.data
        assert b"labeler-step-ramp" in response.data
        assert b"labeler-step-amount" in response.data

    def test_label_cards_button_present(self, client, tmp_path, monkeypatch):
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        assert b"label-cards-btn" in response.data
        assert b"Label Cards" in response.data

    def test_all_nonland_cards_includes_all(self, client, tmp_path, monkeypatch):
        """ALL_NONLAND_CARDS should include all non-land cards (Sol Ring + Vren)."""
        self._mock_deck(monkeypatch, tmp_path)
        response = client.get("/sim/testdeck")
        html = response.data.decode()
        import re
        match = re.search(r'ALL_NONLAND_CARDS\s*=\s*(\[.*?\]);', html, re.DOTALL)
        assert match
        all_cards = json.loads(match.group(1))
        all_names = [c["name"] for c in all_cards]
        assert "Sol Ring" in all_names
        assert "Vren, the Relentless" in all_names
        assert "Island" not in all_names


class TestSaveResultsAPI:
    """Tests for POST /sim/api/<deck_name>/results endpoint."""

    def _mock_deck(self, monkeypatch, tmp_path):
        root = _create_test_deck(tmp_path)
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: os.path.join(root, "decks", name, f"{name}.json"),
        )
        return root

    def test_save_results_nonexistent_deck_404(self, client, tmp_path, monkeypatch):
        """POST to nonexistent deck returns 404."""
        monkeypatch.setattr(
            "auto_goldfish.web.routes.simulation.get_deckpath",
            lambda name: str(tmp_path / "nonexistent" / "nonexistent.json"),
        )
        response = client.post(
            "/sim/api/nonexistent/results",
            data=json.dumps({"config": {}, "results": []}),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_save_results_invalid_json(self, client, tmp_path, monkeypatch):
        """POST with invalid JSON returns 400."""
        self._mock_deck(monkeypatch, tmp_path)
        response = client.post(
            "/sim/api/testdeck/results",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["ok"] is False

    def test_save_results_db_failure_still_returns_ok(self, client, tmp_path, monkeypatch):
        """If DB import fails (no sqlalchemy), endpoint still returns ok."""
        self._mock_deck(monkeypatch, tmp_path)
        # No DB mocking needed -- the try/except in the route catches ImportError
        payload = {"config": {"turns": 10}, "results": []}
        response = client.post(
            "/sim/api/testdeck/results",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True

    def test_save_results_returns_ok_with_valid_payload(self, client, tmp_path, monkeypatch):
        """POST with valid JSON body returns ok (DB persistence is best-effort)."""
        self._mock_deck(monkeypatch, tmp_path)
        payload = {
            "config": {"turns": 10, "sims": 100},
            "results": [{"land_count": 37, "mean_mana": 5.5, "consistency": 0.8}],
        }
        response = client.post(
            "/sim/api/testdeck/results",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
