# Migration Guide — Release 0.9.1

1. Copy the `core/` folder into the project root.
2. Copy the `docs/` files into the existing `docs/` folder.
3. Run:

```cmd
python -m core.test_position_manager
```

4. If the test passes, commit:

```cmd
git add .
git commit -m "Release 0.9.1 - Position manager foundation"
git push
```

Rollback:

```cmd
git reset --hard HEAD~1
```
