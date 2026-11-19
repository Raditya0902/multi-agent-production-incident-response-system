from unittest.mock import Mock

import pytest

from app.database_service import ConnectionPoolExhaustedError, DatabaseService


def test_pool_exhaustion_remains_distinct_and_success_returns_rows(monkeypatch):
    service = DatabaseService("unused", pool_size=1)
    with service._get_session():
        with pytest.raises(ConnectionPoolExhaustedError):
            service.execute_query("SELECT 1")

    connection = Mock()
    connection.execute.return_value = [{"value": 1}]
    monkeypatch.setattr(service.pool, "acquire", lambda timeout: connection)
    assert service.execute_query("SELECT 1") == [{"value": 1}]
    assert service.pool_status()["available"] == 1
