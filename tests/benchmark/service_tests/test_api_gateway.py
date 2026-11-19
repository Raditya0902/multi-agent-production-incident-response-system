from app import api_gateway


def test_unknown_service_returns_unavailable(monkeypatch):
    monkeypatch.setattr(api_gateway, "service_registry", {})
    assert api_gateway.route_request("unknown", "/health") == {
        "error": "service unavailable", "status": 503,
    }
