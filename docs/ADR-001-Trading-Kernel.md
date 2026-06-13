# ADR-001: Trading Kernel

## Status
Accepted

## Context
WhaleStream requires a central decision layer between strategy generation and exchange execution.

## Decision
Introduce `core/trading_kernel.py` as the only valid pathway from signal to execution.

## Consequences
- No signal may bypass the kernel.
- Validation, approval, and trade ticket generation become standardized.
- Future execution layers plug into the kernel rather than directly into strategy modules.
