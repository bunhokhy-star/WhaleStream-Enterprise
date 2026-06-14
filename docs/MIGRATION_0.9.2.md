# Migration Guide — Release 0.9.2

1. Make sure you are on the feature branch:

```cmd
git checkout feature/portfolio-risk
```

2. Copy these folders into the project root:

```text
portfolio
tests
docs
```

3. Run:

```cmd
python -m tests.test_portfolio_risk
```

4. If the test passes, commit:

```cmd
git add .
git commit -m "Release 0.9.2 - Portfolio risk engine"
```
