"""Smoke test: the app starts and serves its start page."""


def test_start_page_returns_200(client):
    """GET / answers with 200 OK."""
    response = client.get("/")
    assert response.status_code == 200
