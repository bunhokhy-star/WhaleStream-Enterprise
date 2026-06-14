# ADR-003: Portfolio Risk Engine

## Status
Accepted

## Context
WhaleStream needs account-level risk governance before live execution can be trusted.

## Decision
Introduce a dedicated `portfolio/` package that evaluates trade risk against portfolio-level constraints.

## Consequences
- Risk decisions move beyond individual trades.
- Portfolio heat can be tracked before execution.
- Duplicate exposure can be blocked.
- Daily loss guards can prevent overtrading.
