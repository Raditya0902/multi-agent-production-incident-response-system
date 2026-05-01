# Incident: Database Connection Pool Exhaustion
**Date:** 2024-10-18
**Severity:** High
**Duration:** 52 minutes
**Affected Users:** 87

## Error
```
sqlalchemy.exc.TimeoutError: Connection pool timeout after 30s
  File "/app/database_service.py", line 89, in execute_query
    result = session.execute(query)
```

## Root Cause
A missing database index on the `orders` table's `user_id` column caused a full table
scan on every order lookup. Under moderate traffic, these slow queries held database
connections open for 20-140 seconds each, exhausting the connection pool (size=5).
With the pool exhausted, all subsequent requests queued and eventually timed out.

## Fix Applied
Two changes were required:
1. Added missing index:
```sql
CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);
```
2. Increased connection pool size as a temporary relief while the index was being built:
```python
# Before
engine = create_engine(DATABASE_URL, pool_size=5)

# After
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=10, pool_timeout=60)
```

## Timeline
- 16:30 - Response times begin degrading
- 16:45 - Connection pool timeouts appear in logs
- 16:52 - Slow query identified via pg_stat_activity
- 17:05 - Index creation started (non-blocking)
- 17:22 - Full recovery confirmed

## Prevention
- Add slow query monitoring with alerts for queries >1s
- Automate index coverage checks in CI using pganalyze or similar
- Load test with realistic concurrency before major releases
