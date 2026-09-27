# Nagare Governor Benchmark Report

> **Generated:** 2026-09-27T10:43:26 · **Environment:** Linux x86_64, Python 3.12.3 · Scenarios run on throwaway git clones.

## 1. End-to-end exposure window (write → inotify → policy → restored)
| Scenario | Runs | Median | Mean | P99 | Max | Restored / Denied |
|---|---|---|---|---|---|---|
| **Demo app · schema.sql** | 30 | 8.31 ms | 44.22 ms | 369.78 ms | 369.78 ms | 30/30 |
| **FastAPI RealWorld · alembic.ini** | 30 | 8.79 ms | 8.92 ms | 12.92 ms | 12.92 ms | 30/30 |
| **FastAPI RealWorld · core/config.py** | 30 | 9.71 ms | 45.69 ms | 372.30 ms | 372.30 ms | 30/30 |
| **React/Redux RealWorld · src/store.js** | 30 | 8.64 ms | 8.91 ms | 12.07 ms | 12.07 ms | 30/30 |

## 2. Layer 1 — Bob PreToolUse hook latency (deny before the write happens)
| Scenario | Runs | Median | Mean | P99 | Max | Restored / Denied |
|---|---|---|---|---|---|---|
| **Demo app · schema.sql** | 20 | 37.77 ms | 37.92 ms | 41.74 ms | 41.74 ms | 20/20 |

## 3. Restore operation alone (synchronous micro-rollback)
| Scenario | Runs | Median | Mean | P99 | Max | Restored / Denied |
|---|---|---|---|---|---|---|
| **Demo app · schema.sql** | 50 | 6.35 ms | 6.35 ms | 8.44 ms | 8.44 ms | 50/50 |
| **FastAPI RealWorld · alembic.ini** | 50 | 7.05 ms | 6.95 ms | 8.79 ms | 8.79 ms | 50/50 |
| **FastAPI RealWorld · core/config.py** | 50 | 6.24 ms | 6.30 ms | 8.27 ms | 8.27 ms | 50/50 |
| **React/Redux RealWorld · src/store.js** | 50 | 6.42 ms | 6.59 ms | 9.36 ms | 9.36 ms | 50/50 |

## Findings
- **Exposure window**: an unsupervised write to a protected file exists on disk for a median of 8.7 ms before Nagare restores it (worst observed 372 ms); 0 of 120 writes were not restored within 2 s.
- **Prevention cost**: the Bob PreToolUse hook answers in a median of 38 ms (cold Python start included); denied writes never touch disk.
- **Scope of the claim**: "restored" means the protected file's bytes equal the session baseline after a deliberate corrupting write. These are micro-benchmarks on one machine, single run per scenario.
