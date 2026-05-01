# Incident: AttributeError — NoneType Method Call in user_service.py
**Date:** 2024-10-30
**Severity:** Medium
**Duration:** 27 minutes
**Affected Users:** 14

## Error
```
AttributeError: 'NoneType' object has no attribute 'email'
  File "/app/user_service.py", line 113, in send_notification
    recipient = user_repo.find_by_id(user_id).email
```

## Root Cause
`user_repo.find_by_id()` returns `None` when the user ID does not exist in the database.
The calling code assumed it would always find a valid user, so it chained `.email`
directly without a None check. This occurred when deleted/anonymized user accounts
were still referenced in a notification queue that hadn't been cleaned up.

## Fix Applied
Added a None guard before attribute access:
```python
# Before
recipient = user_repo.find_by_id(user_id).email

# After
user = user_repo.find_by_id(user_id)
if user is None:
    logger.warning(f"User {user_id} not found, skipping notification")
    return
recipient = user.email
```

## Timeline
- 11:05 - Notification failures detected in logs
- 11:18 - Error traced to deleted user accounts still in queue
- 11:27 - Fix deployed
- 11:32 - Queue drained successfully

## Prevention
- Use Optional[User] return type annotation to force callers to handle None
- Add a cleanup job to remove stale notification queue entries for deleted users
- Enable mypy strict None checks to catch this class of error at lint time
