from types import SimpleNamespace
from unittest.mock import Mock

from app.notification_service import NotificationService


def test_known_user_still_receives_welcome_after_missing_user(monkeypatch):
    users = {"known": SimpleNamespace(email="user@example.com")}
    service = NotificationService(Mock(find_by_id=users.get))
    send = Mock()
    monkeypatch.setattr(service, "_send_smtp", send)
    service.send_welcome_email("missing")
    service.send_welcome_email("known")
    send.assert_called_once()
    address, message = send.call_args.args
    assert address == message["To"] == "user@example.com"
    assert message["Subject"] == "Welcome to the platform!"
