import pytest

from app import api_gateway


def test_registered_service_preserves_path_and_payload(monkeypatch):
    monkeypatch.setattr(api_gateway, "service_registry", {"orders": "orders.internal"})
    payload = {"order": 0}
    assert api_gateway.route_request("orders", "/lookup", payload) == {
        "host": "orders.internal", "path": "/lookup", "payload": payload,
    }
    with pytest.raises(ValueError):
        api_gateway.route_request("", "/lookup")
