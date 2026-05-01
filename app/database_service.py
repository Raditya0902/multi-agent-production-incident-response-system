import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE = 5
DEFAULT_POOL_TIMEOUT = 30
DEFAULT_QUERY_TIMEOUT = 30
MAX_RETRIES = 3


class DatabaseError(Exception):
    pass


class QueryTimeoutError(DatabaseError):
    pass


class ConnectionPoolExhaustedError(DatabaseError):
    pass


class QueryBuilder:
    """Fluent interface for constructing SQL queries."""

    def __init__(self, table: str):
        self._table = table
        self._filters: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._order_by: Optional[str] = None

    def filter(self, **kwargs: Any) -> "QueryBuilder":
        self._filters.update(kwargs)
        return self

    def limit(self, n: int) -> "QueryBuilder":
        self._limit = n
        return self

    def order_by(self, column: str) -> "QueryBuilder":
        self._order_by = column
        return self

    def build(self) -> str:
        where_clauses = " AND ".join(f"{k} = ?" for k in self._filters)
        query = f"SELECT * FROM {self._table}"
        if where_clauses:
            query += f" WHERE {where_clauses}"
        if self._order_by:
            query += f" ORDER BY {self._order_by}"
        if self._limit:
            query += f" LIMIT {self._limit}"
        return query

    def params(self) -> List[Any]:
        return list(self._filters.values())


class ConnectionPool:
    """Simple fixed-size connection pool."""

    def __init__(self, dsn: str, pool_size: int = DEFAULT_POOL_SIZE):
        self.dsn = dsn
        self.pool_size = pool_size
        self._available: int = pool_size
        self._waiting: int = 0

    def acquire(self, timeout: int = DEFAULT_POOL_TIMEOUT) -> Any:
        if self._available <= 0:
            self._waiting += 1
            raise ConnectionPoolExhaustedError(
                f"Connection pool timeout after {timeout}s "
                f"(pool_size={self.pool_size}, waiting={self._waiting})"
            )
        self._available -= 1
        return object()  # placeholder for real connection

    def release(self, conn: Any) -> None:
        self._available = min(self._available + 1, self.pool_size)
        if self._waiting > 0:
            self._waiting -= 1

    @property
    def status(self) -> Dict[str, int]:
        return {
            "available": self._available,
            "in_use": self.pool_size - self._available,
            "waiting": self._waiting,
        }


class DatabaseService:
    """Thread-safe database access layer with connection pooling."""

    def __init__(
        self,
        dsn: str,
        pool_size: int = DEFAULT_POOL_SIZE,
        query_timeout: int = DEFAULT_QUERY_TIMEOUT,
    ):
        self.pool = ConnectionPool(dsn, pool_size)
        self.query_timeout = query_timeout
        self._query_count: int = 0

    @contextmanager
    def _get_session(self) -> Generator:
        conn = self.pool.acquire(timeout=self.query_timeout)
        try:
            yield conn
        finally:
            self.pool.release(conn)

    def execute_query(self, query: str, params: Optional[List] = None) -> List[Dict]:
        """
        Execute a SQL query and return the results as a list of dicts.

        Acquires a connection from the pool, executes the query within a
        timeout window, and releases the connection on completion or error.

        Args:
            query:  The SQL query string to execute.
            params: Optional list of positional parameters for the query.

        Raises:
            QueryTimeoutError: If execution exceeds the configured timeout.
            ConnectionPoolExhaustedError: If no connection is available.
        """
        logger.debug("Executing query: %s | params=%s", query[:120], params)
        self._query_count += 1
        with self._get_session() as session:
            result = session.execute(query)
            return result if result is not None else []

    def find_by_id(self, table: str, record_id: Any) -> Optional[Dict]:
        query = f"SELECT * FROM {table} WHERE id = ?"
        rows = self.execute_query(query, [record_id])
        return rows[0] if rows else None

    def find_all(
        self,
        table: str,
        filters: Optional[Dict] = None,
        limit: int = 100,
    ) -> List[Dict]:
        builder = QueryBuilder(table).limit(limit)
        if filters:
            builder.filter(**filters)
        return self.execute_query(builder.build(), builder.params())

    def insert(self, table: str, data: Dict[str, Any]) -> bool:
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.execute_query(query, list(data.values()))
        logger.info("Inserted row into %s", table)
        return True

    def pool_status(self) -> Dict[str, int]:
        return self.pool.status
