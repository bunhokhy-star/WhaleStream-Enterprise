# ADR-002: Position Manager

## Status
Accepted

## Context
WhaleStream needs a dedicated component to manage open trade lifecycle after execution.

## Decision
Introduce a `PositionManager` responsible for:
- Tracking open positions
- Applying break-even logic
- Applying trailing stop logic
- Applying partial take-profit logic
- Publishing position lifecycle events

## Consequences
The strategy engine remains separate from position management.
Execution integration can be added later without rewriting lifecycle logic.
