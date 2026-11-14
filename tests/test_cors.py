"""CORS and system endpoint tests."""


def preflight(client, origin):
    return client.options("/auth/login", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, Authorization",
    })


def test_vite_dev_origin_is_allowed(client):
    response = preflight(client, "http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unknown_origin_is_not_allowed(client):
    response = preflight(client, "http://evil.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_allowed_origin(client):
    response = client.get("/", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )


def test_health_check_uses_test_database(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"].endswith("_test")
