# WhaleStream Enterprise Release 0.9.1

## Name
Position Manager Foundation

## Purpose
Release 0.9.1 introduces simulated position lifecycle management.

## New Components
- `core/position.py`
- `core/position_manager.py`
- `core/breakeven.py`
- `core/trailing_stop.py`
- `core/partial_take_profit.py`
- `core/test_position_manager.py`

## Acceptance Test

Run:

```cmd
python -m core.test_position_manager
```

Expected:

```text
STATUS: POSITION MANAGER TEST PASSED
```

## What This Release Does Not Do
- It does not modify live Bybit stop-losses yet.
- It does not close real positions yet.
- It simulates position lifecycle logic safely.

Live exchange synchronization will come later.

## Recommended Commit

```cmd
git add .
git commit -m "Release 0.9.1 - Position manager foundation"
git push
```
