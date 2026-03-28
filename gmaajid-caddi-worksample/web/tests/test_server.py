"""Tests for FastAPI server — REST API endpoints."""

import pytest
from fastapi.testclient import TestClient
from web.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestRESTAPI:
    def test_index_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_graph_endpoint(self, client):
        response = client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "alerts" in data

    def test_tutorials_list(self, client):
        response = client.get("/api/tutorials")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have the 6 tutorials from web/tutorials/
        assert len(data) >= 1

    def test_tutorial_by_id(self, client):
        response = client.get("/api/tutorials")
        tutorials = response.json()
        if tutorials:
            tid = tutorials[0]["id"]
            response = client.get(f"/api/tutorials/{tid}")
            assert response.status_code == 200
            assert response.json()["id"] == tid

    def test_tutorial_not_found(self, client):
        response = client.get("/api/tutorials/nonexistent")
        assert response.status_code == 404
