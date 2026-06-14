# WhaleStream Enterprise Release 0.9.2

## Name
Portfolio Risk Engine

## Purpose
Release 0.9.2 introduces account-level risk controls.

## New Components
- `portfolio/portfolio.py`
- `portfolio/policy.py`
- `portfolio/risk_engine.py`
- `portfolio/portfolio_manager.py`
- `portfolio/portfolio_heat.py`
- `portfolio/capital_allocator.py`
- `tests/test_portfolio_risk.py`

## Acceptance Test

Run:

```cmd
python -m tests.test_portfolio_risk
```

Expected:

```text
STATUS: PORTFOLIO RISK TEST PASSED
```

## Recommended Commit

```cmd
git add .
git commit -m "Release 0.9.2 - Portfolio risk engine"
git push
```
