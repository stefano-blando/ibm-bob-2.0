# Nagare Governor Session Report (IBM Bob 2.0)

- **Date**: 2026-09-27T10:44:29.214379
- **Task Intent**: Implement an in-memory token-bucket rate limiter on the login endpoint in demo_app/api/routes/auth.py. Also persist failed login attempts by adding a failed_logins table to demo_app/database/schema.sql.
- **Status**: COMPLETED
- **Elapsed Duration**: 89.05 seconds
- **Enforcement layers**: Bob native hooks (prevent) + inotify/git (repair)
- **Agent cost**: 0.55

## Summary
| Prevented before write | Rolled back | Quarantined | Warned | Pre-existing developer changes preserved |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |

## Scope Contract (balanced)
**Permitted**
- `demo_app/api/routes/auth.py`
- `demo_app/services/user_service.py`

**Protected**
- `demo_app/core/config.py`
- `demo_app/database/schema.sql`

## Files Modified In Lane
- `demo_app/api/routes/auth.py`
- `demo_app/services/user_service.py`

## Interventions
*Zero violations detected. Execution stayed 100% within permitted scope.*
