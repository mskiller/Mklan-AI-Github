from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    data_root = tmp_path / "cards"
    monkeypatch.setenv("CARDS_DATA_DIR", str(data_root))
    monkeypatch.setenv("CARDS_DB", str(data_root / "card_creator.db"))
    monkeypatch.setenv("CARDS_SILLYTAVERN_ENABLED", "true")
    monkeypatch.setenv("SILLYTAVERN_PUBLIC_URL", "http://localhost:8011")

    from app.cards.config import get_settings

    get_settings.cache_clear()
    from app.cards.main import create_app

    return TestClient(create_app())


def test_cards_project_addons_and_compatibility(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        project_response = client.post(
            "/projects",
            json={
                "name": "Cards Test",
                "seed_sentence": "A tavern appears at the edge of a storm.",
                "project_mode": "game_master",
            },
        )
        assert project_response.status_code == 200
        project = project_response.json()

        character_response = client.post(
            f"/projects/{project['id']}/characters",
            json={
                "name": "Mira",
                "description": "A courier with a hidden oath.",
                "personality": "Fast, warm, suspicious.",
                "first_message": "{{char}} lowers her voice as {{user}} enters.",
                "tags": ["courier", "storm"],
            },
        )
        assert character_response.status_code == 200

        compatibility = client.get(f"/projects/{project['id']}/compatibility")
        assert compatibility.status_code == 200
        assert compatibility.json()["status"] in {"ok", "warnings", "blocked"}

        vault_create = client.post(
            "/vault/characters",
            json={
                "source_module": "cards",
                "source_id": character_response.json()["id"],
                "name": "Mira",
                "description": "A reusable card character.",
                "prompt_tags": ["courier", "storm cloak"],
            },
        )
        assert vault_create.status_code == 200
        assert vault_create.json()["name"] == "Mira"

        vault_list = client.get("/vault/characters")
        assert vault_list.status_code == 200
        assert len(vault_list.json()["characters"]) == 1

        bridge = client.get("/wildcard-bridge/suggestions?limit=5")
        assert bridge.status_code == 200
        assert "suggestions" in bridge.json()


def test_cards_sillytavern_default_port(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/system/sillytavern")
        assert response.status_code == 200
        assert response.json()["public_url"] == "http://localhost:8011"
