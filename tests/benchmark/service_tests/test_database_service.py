from unittest.mock import Mock

import pytest

from app.database_service import DatabaseService, QueryTimeoutError


def test_query_timeout_uses_service_error_and_releases_connection(monkeypatch):
    service = DatabaseService("unused", pool_size=1)
    connection = Mock()
    connection.execute.side_effect = TimeoutError("query timed out")
    def acquire(timeout):
        service.pool._available -= 1
        return connection

    monkeypatch.setattr(service.pool, "acquire", acquire)

    with pytest.raises(QueryTimeoutError):
        service.execute_query("SELECT 1")

    connection.execute.assert_called_once_with("SELECT 1")
    assert service.pool_status()["available"] == 1
