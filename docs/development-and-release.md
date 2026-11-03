# 开发、测试与发布

## 1. 本地开发

```bash
poetry install --with dev
poetry run ruff check .
poetry run pyright
poetry run pytest
```

## 2. 常用测试建议

- 先跑变更相关测试（模块级）
- 再跑全量 `pytest`
- 变更配置/轮转/队列逻辑时，优先覆盖对应 `tests/test_*` 用例

## 3. 调试建议

- 启动模式：`poetry run python launch_camoufox.py --debug`
- API 观察：`/health`、`/v1/queue`、`/ws/logs`
- Function Calling 排障：开启 `FUNCTION_CALLING_DEBUG` + 精确 `FC_DEBUG_*`

## 4. CI/CD（仓库工作流）

- PR 检查：lint + type check + tests
- Release：支持 tag / nightly / 手动触发
- Upstream Sync：同步上游并自动建 PR

## 5. 发布最小流程（建议）

```bash
# 1) 保证主分支干净并通过测试
poetry run ruff check .
poetry run pyright
poetry run pytest

# 2) 打 tag
git tag v0.1.0
git push origin v0.1.0
```

