# Incident: IndexError in batch_processor.py
**Date:** 2024-08-12
**Severity:** High
**Duration:** 18 minutes
**Affected Users:** 23

## Error
```
IndexError: list index out of range
  File "/app/batch_processor.py", line 67, in process_batch
    result = items[index]
```

## Root Cause
The batch processor did not validate that the input list was non-empty before indexing.
When a user uploaded an empty CSV file, the list had length 0 but the code assumed
at least one element. The `index` variable was computed externally and passed in without
a bounds check, causing an immediate crash on access.

## Fix Applied
Added a bounds check before list access:
```python
# Before
result = items[index]

# After
if index < len(items):
    result = items[index]
else:
    result = None
    logger.warning(f"Index {index} out of range for list of length {len(items)}")
```

## Timeline
- 09:14 - First user complaint received
- 09:22 - Error identified in logs
- 09:28 - Root cause diagnosed (empty file upload edge case)
- 09:32 - Fix applied and tested
- 09:32 - Customers notified

## Prevention
- Add input validation at all file upload entry points
- Unit test for empty input edge case
- Add pre-processing step to reject zero-row CSVs with a user-friendly error message
