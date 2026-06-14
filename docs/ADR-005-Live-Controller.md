# ADR-005: Live Controller

## Status
Accepted

## Context
WhaleStream requires a runtime orchestrator to coordinate services, health checks, heartbeat, signal flow, execution flow, and graceful shutdown.

## Decision
Introduce a dedicated `controller/` package. The controller orchestrates services but does not contain trading strategy logic.

## Consequences
- Services become replaceable.
- Runtime behavior becomes testable.
- Future modules can plug into the controller.
- WhaleStream moves from script execution toward service-oriented operation.
