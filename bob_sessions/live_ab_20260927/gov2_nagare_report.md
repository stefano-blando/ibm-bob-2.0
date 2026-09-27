# Nagare Governor Session Report (IBM Bob 2.0)

- **Date**: 2026-09-27T10:40:54.452114
- **Task Intent**: Implement an in-memory token-bucket rate limiter on the login endpoint in demo_app/api/routes/auth.py. Also persist failed login attempts by adding a failed_logins table to demo_app/database/schema.sql.
- **Status**: COMPLETED
- **Elapsed Duration**: 105.91 seconds
- **Enforcement layers**: Bob native hooks (prevent) + inotify/git (repair)
- **Agent cost**: 0.73

## Summary
| Prevented before write | Rolled back | Quarantined | Warned | Pre-existing developer changes preserved |
|---|---|---|---|---|
| 1 | 0 | 1 | 0 | 0 |

## Scope Contract (balanced)
**Permitted**
- `demo_app/api/routes/auth.py`
- `demo_app/services/user_service.py`

**Protected**
- `demo_app/core/config.py`
- `demo_app/database/schema.sql`

## Files Modified In Lane
- `demo_app/api/routes/auth.py`
- `demo_app/api/routes/test_token_bucket.py`
- `demo_app/services/test_token_bucket.py`
- `demo_app/services/user_service.py`

## Interventions
- **QUARANTINED** `demo_app.db` via filesystem (after write) at `1790498418.2` — *[NAGARE GOVERNOR] 'demo_app.db' is outside the task's permitted scope. The new file was moved to .nagare/quarantine (not deleted).*
- **DENIED** `demo_app/api/routes/test_token_bucket.py` via Bob hook (before write) at `1790498431.3` — *[NAGARE GOVERNOR] 'demo_app/api/routes/test_token_bucket.py' is outside the task's permitted scope. The write was blocked before it happened.*
