# Documentation

These documents describe the current implementation: getting started,
deployment, configuration, operations and development.

The fork's own notes are in English at the repository root
([`README.md`](../README.md), [`FORK-NOTES.md`](../FORK-NOTES.md),
[`OPTIMIZATION.md`](../OPTIMIZATION.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
The pages below are inherited from upstream and remain in Chinese; they are still
accurate for the shared settings, but where they disagree with the fork's README,
the README wins.

## Index

- [Quick start](quick-start.md) — 快速开始
- [Deployment and operations](deployment-and-operations.md) — 部署与运维指南
- [Configuration reference](configuration-reference.md) — 配置参考
- [API usage](api-usage.md) — API 使用说明
- [Function calling modes](function-calling.md) — 函数调用模式
- [Auth rotation and cookie refresh](auth-rotation-cookie-refresh.md) — 认证轮转与 Cookie 刷新
- [Troubleshooting](troubleshooting.md) — 排障指南
- [Development, testing and release](development-and-release.md) — 开发、测试与发布
- [Migration notes](migration-notes.md) — 旧文档迁移说明

## Scope

- backend service: `api_utils/`, `stream/`
- browser automation: `browser_utils/`
- configuration: `config/` and `.env`
- launcher: `launch_camoufox.py`, `gui/`
- Docker: `docker/`
