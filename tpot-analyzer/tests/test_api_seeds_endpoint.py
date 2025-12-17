from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.accounts import accounts_bp


@pytest.fixture
def seeds_app(monkeypatch, tmp_path: Path) -> Flask:
    """Flask app with /api/seeds endpoints wired against temp seed state files."""
    import src.graph.seeds as seeds
    import src.api.routes.accounts as accounts_routes

    preset_file = tmp_path / "seed_presets.json"
    preset_file.write_text(json.dumps({"adi_tpot": ["alice"]}))
    state_file = tmp_path / "graph_settings.json"
    state_file.write_text(json.dumps({}))

    monkeypatch.setattr(seeds, "_DEFAULT_PRESET_FILE", preset_file, raising=False)
    monkeypatch.setattr(seeds, "_SEED_STATE_FILE", state_file, raising=False)

    # Reset cached stores between tests.
    accounts_routes._tag_store = None
    accounts_routes._search_index = None

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(accounts_bp)
    return app


@pytest.mark.unit
def test_seeds_get_returns_state(seeds_app: Flask) -> None:
    client = seeds_app.test_client()
    resp = client.get("/api/seeds")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["active_list"] == "adi_tpot"
    assert payload["lists"]["adi_tpot"] == ["alice"]
    assert payload["preset_names"] == ["adi_tpot"]
    assert "settings" in payload


@pytest.mark.unit
def test_seeds_post_updates_settings(seeds_app: Flask) -> None:
    client = seeds_app.test_client()
    resp = client.post("/api/seeds", json={"settings": {"auto_include_shadow": False}})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]["settings"]["auto_include_shadow"] is False


@pytest.mark.unit
def test_seeds_post_saves_and_activates_list(seeds_app: Flask) -> None:
    client = seeds_app.test_client()
    resp = client.post(
        "/api/seeds",
        json={"name": "my_list", "seeds": ["bob", "@carol"], "set_active": True},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]["active_list"] == "my_list"
    assert payload["state"]["lists"]["my_list"] == ["bob", "carol"]

