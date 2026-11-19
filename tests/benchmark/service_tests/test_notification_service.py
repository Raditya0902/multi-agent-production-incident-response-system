from unittest.mock import Mock

from app.notification_service import NotificationService


def test_missing_user_skips_welcome_email(monkeypatch):
    service = NotificationService(Mock(find_by_id=Mock(return_value=None)))
    send = Mock()
    monkeypatch.setattr(service, "_send_smtp", send)
    service.send_welcome_email("missing")
    send.assert_not_called()
    assert service._sent == []
