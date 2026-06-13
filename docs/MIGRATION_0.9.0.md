# Migration Guide — Release 0.9.0

1. Copy the `core/` folder into the project root.
2. Copy the `docs/` files into the existing `docs/` folder or create it.
3. Run:

```cmd
python core\test_kernel.py
```

4. If the test passes, commit:

```cmd
git add .
git commit -m "Release 0.9.0 - Trading kernel foundation"
git push
```

Rollback:

```cmd
git reset --hard HEAD~1
```
