# Migration Guide — Release 0.9.4 Apollo

1. Make sure you are on the feature branch:

```cmd
git checkout feature/live-controller
```

2. Copy these folders into the project root:

```text
controller
tests
docs
```

3. Run:

```cmd
python -m tests.test_live_controller
```

4. If the test passes, commit:

```cmd
git add .
git commit -m "Release 0.9.4 - Apollo live controller"
```
