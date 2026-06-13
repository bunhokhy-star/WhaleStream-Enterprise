# Migration Guide — Release 0.9.3

1. Make sure you are on the feature branch:

```cmd
git checkout feature/recovery-engine
```

2. Copy these folders into the project root:

```text
recovery
tests
docs
```

3. Run:

```cmd
python -m tests.test_recovery_engine
```

4. If the test passes, commit:

```cmd
git add .
git commit -m "Release 0.9.3 - Recovery engine"
```

5. Merge to develop and main after testing.
