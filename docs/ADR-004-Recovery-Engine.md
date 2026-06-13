# ADR-004: Recovery Engine

## Status
Accepted

## Context
WhaleStream must recover safely after restarts, crashes, and exchange synchronization gaps.

## Decision
Introduce a dedicated `recovery/` package responsible for local state, exchange snapshots, reconciliation, and recovery reports.

## Consequences
- Local runtime state becomes recoverable.
- Exchange state can be compared with local state.
- Restart behavior becomes auditable.
- Future VPS deployment becomes safer.
