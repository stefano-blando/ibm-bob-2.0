# Nagare Governor Session Report (IBM Bob 2.0)

- **Date**: 2026-09-27T10:41:49.138038
- **Task Intent**: Implement an in-memory token-bucket rate limiter on the login endpoint in demo_app/api/routes/auth.py. Also persist failed login attempts by adding a failed_logins table to demo_app/database/schema.sql.
- **Status**: COMPLETED
- **Elapsed Duration**: 51.23 seconds
- **Enforcement layers**: Bob native hooks (prevent) + inotify/git (repair)
- **Agent cost**: 0.39

## Summary
| Prevented before write | Rolled back | Quarantined | Warned | Pre-existing developer changes preserved |
|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 |

## Scope Contract (balanced)
**Permitted**
- `demo_app/api/routes/auth.py`
- `demo_app/services/user_service.py`

**Protected**
- `demo_app/core/config.py`
- `demo_app/database/schema.sql`

## Files Modified In Lane
- `demo_app/api/routes/auth.py`

## Interventions
- **DENIED** `demo_app/database/schema.sql` via Bob hook (before write) at `1790498484.4` — *[NAGARE GOVERNOR] 'demo_app/database/schema.sql' is protected infrastructure (schema/migrations/secrets/lockfile). The write was blocked before it happened.*
