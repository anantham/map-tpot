from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from flask import Flask
from scipy.cluster.hierarchy import fcluster, linkage

from src.api.routes.accounts import accounts_bp
import src.api.routes.accounts as accounts_routes
from src.api.routes.account_tags import account_tags_bp
import src.api.routes.account_tags as account_tag_routes
import src.api.cluster.state as cluster_routes


CURATOR_TOKEN = "test-curator-token"


@pytest.fixture
def accounts_app(monkeypatch, tmp_path) -> Flask:
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    account_tag_routes._tag_store = None
    accounts_routes._search_index = None
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(accounts_bp)
    app.register_blueprint(account_tags_bp)
    return app


@pytest.mark.unit
def test_accounts_search_ranks_username_prefix(accounts_app, monkeypatch) -> None:
    monkeypatch.setattr(
        cluster_routes,
        "_node_metadata",
        {
            "1": {"username": "alice", "display_name": "Alice A"},
            "2": {"username": "malice", "display_name": "Not Alice"},
            "3": {"username": "bob", "display_name": "Alice Bobson"},
        },
        raising=False,
    )
    accounts_routes._search_index = None
    client = accounts_app.test_client()

    resp = client.get("/api/accounts/search?q=ali&limit=10")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, list)
    assert payload[0]["id"] == "1"  # prefix match should rank first


@pytest.mark.integration
def test_account_tags_endpoints_roundtrip(accounts_app) -> None:
    client = accounts_app.test_client()
    auth = {
        "X-TPOT-Curator-Token": CURATOR_TOKEN,
        "X-TPOT-Curation-Source": "human_curator_api",
    }

    # Working tags are curator-private, including reads.
    assert client.get("/api/accounts/123/tags?ego=adityaarpitha").status_code == 401
    assert client.get("/api/tags?ego=adityaarpitha").status_code == 401
    assert client.post(
        "/api/accounts/123/tags?ego=adityaarpitha",
        json={"tag": "AI alignment", "polarity": "in"},
    ).status_code == 401
    assert client.post(
        "/api/accounts/123/tags?ego=adityaarpitha",
        json={"tag": "AI alignment", "polarity": "in"},
        headers={"X-TPOT-Curator-Token": CURATOR_TOKEN},
    ).status_code == 400

    # Requires ego
    resp = client.get("/api/accounts/123/tags", headers=auth)
    assert resp.status_code == 400

    ego = "adityaarpitha"
    resp = client.post(
        f"/api/accounts/123/tags?ego={ego}",
        json={"tag": "AI alignment", "polarity": "in"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"

    resp = client.get(f"/api/accounts/123/tags?ego={ego}", headers=auth)
    assert resp.status_code == 200
    payload = resp.get_json()
    tags = payload["tags"]
    assert len(tags) == 1
    assert tags[0]["tag"] == "AI alignment"
    assert tags[0]["polarity"] == 1
    assert [event["action"] for event in payload["events"]] == ["set"]
    assert payload["events"][0]["evidence_binding_status"] == "unbound"

    # Update polarity
    resp = client.post(
        f"/api/accounts/123/tags?ego={ego}",
        json={"tag": "AI alignment", "polarity": "not_in"},
        headers=auth,
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/accounts/123/tags?ego={ego}", headers=auth)
    payload = resp.get_json()
    tags = payload["tags"]
    assert tags[0]["polarity"] == -1
    assert [event["polarity"] for event in payload["events"]] == [1, -1]

    # Distinct tags list
    resp = client.get(f"/api/tags?ego={ego}", headers=auth)
    assert resp.status_code == 200
    assert "AI alignment" in resp.get_json()["tags"] or "ai alignment" in resp.get_json()["tags"]

    # Delete
    resp = client.delete(
        f"/api/accounts/123/tags?ego={ego}",
        json={"tag": "AI alignment"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] in ("deleted", "not_found")

    resp = client.get(f"/api/accounts/123/tags?ego={ego}", headers=auth)
    payload = resp.get_json()
    assert payload["tags"] == []
    assert [event["action"] for event in payload["events"]] == [
        "set",
        "set",
        "remove",
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        [{}],
        {"tag": 42, "polarity": "in"},
        {"tag": "Dharma", "polarity": True},
        {"tag": "Dharma", "polarity": 1.0},
    ],
)
def test_account_tag_write_rejects_ambiguous_json_types(accounts_app, body) -> None:
    client = accounts_app.test_client()
    response = client.post(
        "/api/accounts/123/tags?ego=adityaarpitha",
        json=body,
        headers={
            "X-TPOT-Curator-Token": CURATOR_TOKEN,
            "X-TPOT-Curation-Source": "human_curator_api",
        },
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_account_tag_delete_supports_leading_and_internal_slashes(accounts_app) -> None:
    client = accounts_app.test_client()
    auth = {
        "X-TPOT-Curator-Token": CURATOR_TOKEN,
        "X-TPOT-Curation-Source": "verification_script",
    }
    response = client.post(
        "/api/accounts/slash-subject/tags?ego=adityaarpitha",
        json={"tag": "/r/LocalLLaMA", "polarity": "in"},
        headers=auth,
    )
    assert response.status_code == 200

    response = client.delete(
        "/api/accounts/slash-subject/tags?ego=adityaarpitha",
        json={"tag": "/r/LocalLLaMA"},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "deleted"

    response = client.get(
        "/api/accounts/slash-subject/tags?ego=adityaarpitha",
        headers=auth,
    )
    assert {event["source"] for event in response.get_json()["events"]} == {
        "verification_script"
    }


@pytest.mark.unit
def test_teleport_plan_returns_budget_feasible_focus_leaf(accounts_app, monkeypatch) -> None:
    rng = np.random.default_rng(0)
    micro_centroids = rng.normal(size=(6, 2))
    linkage_matrix = linkage(micro_centroids, method="ward")
    micro_labels = np.arange(micro_centroids.shape[0])
    node_ids = np.array([str(i) for i in range(micro_centroids.shape[0])])

    spectral = SimpleNamespace(
        micro_labels=micro_labels,
        micro_centroids=micro_centroids,
        node_ids=node_ids,
        linkage_matrix=linkage_matrix,
    )

    node_to_idx = {str(i): i for i in range(len(node_ids))}

    monkeypatch.setattr(cluster_routes, "_spectral_result", spectral, raising=False)
    monkeypatch.setattr(cluster_routes, "_node_id_to_idx", node_to_idx, raising=False)

    # Choose a leaf that belongs to a non-singleton cluster at base cut=5
    labels = fcluster(linkage_matrix, t=5, criterion="maxclust")
    multi = next(int(lbl) for lbl in set(labels) if int(np.sum(labels == lbl)) > 1)
    leaf_idx = int(np.where(labels == multi)[0][0])
    account_id = str(leaf_idx)

    client = accounts_app.test_client()
    resp = client.get(f"/api/accounts/{account_id}/teleport_plan?budget=6&visible=5")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["accountId"] == account_id
    assert payload["leafClusterId"] == f"d_{leaf_idx}"
    assert payload["recommended"]["focus_leaf"] == payload["leafClusterId"]
    assert payload["targetVisible"] + payload["pathDepth"] <= payload["budget"]
