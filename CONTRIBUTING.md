# 贡献指南

感谢你参与 AI Studio Proxy API 的改进。

## 本地开发准备

```bash
git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
cd AIstudioProxyAPI
poetry install --with dev
```

## 提交前检查（必须）

```bash
poetry run ruff check .
poetry run pyright
poetry run pytest
```

如涉及前端改动，请额外执行：

```bash
cd static/frontend
npm ci
npm run build
npm run test
```

## 分支与提交规范

- 新功能：`feat/...`
- 缺陷修复：`fix/...`
- 文档改动：`docs/...`
- 重构：`refactor/...`

建议使用 Conventional Commits：

- `feat:` 新能力
- `fix:` 缺陷修复
- `docs:` 文档更新
- `refactor:` 重构
- `test:` 测试改进
- `chore:` 工程性调整

## Pull Request 要求

- 说明变更动机、核心实现和影响范围。
- 如涉及配置/接口变更，必须更新文档。
- 引入新环境变量时，必须同步更新 `.env.example`。
- 通过 CI 检查后再请求合并。

## CI/CD 工作流

- `PR Check`：运行 lint/typecheck/tests。
- `Release`：tag 或手动触发发布。
- `Sync with Upstream`：从上游仓库同步提交并自动建 PR。

## 参考文档

- [快速开始](docs/quick-start.md)
- [配置参考](docs/configuration-reference.md)
- [排障指南](docs/troubleshooting.md)
- [开发、测试与发布](docs/development-and-release.md)

## Issue 反馈建议

请尽量提供：

- 复现步骤
- 期望行为与实际行为
- Python 版本 / 操作系统
- 相关日志（如 `logs/`、`errors_py/`）
