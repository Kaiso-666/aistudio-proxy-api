# 快速开始

> 目标：用最短路径把服务跑起来，并完成一次可用请求。

## 1. 运行前确认

- Python `>=3.9,<4.0`（推荐 3.10/3.11）
- Poetry
- 可访问 Google AI Studio 的网络（如需要可配置 `UNIFIED_PROXY_CONFIG`）
- 首次登录建议有图形界面（或使用你已经准备好的 `auth_profiles/active/*.json`）

## 2. 安装依赖

```bash
git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
cd AIstudioProxyAPI
poetry install --with dev
```

> 可选：如果你希望用项目脚本一键安装，可使用 `scripts/install.sh`（Linux/macOS）或 `scripts/install.ps1`（Windows）。

## 3. 初始化配置

```bash
cp .env.example .env
```

建议至少先检查这些配置：

- `PORT`：主 API 端口（默认 `2048`）
- `STREAM_PORT`：流代理端口（默认 `3120`，设 `0` 可关闭）
- `UNIFIED_PROXY_CONFIG`：统一代理（有网络限制时必填）
- `LAUNCH_MODE`：建议首次使用 `debug`
- `AUTO_SAVE_AUTH`：首次登录调试时可设为 `true`

## 4. 首次认证（推荐流程）

首次运行建议用可见浏览器进行登录并保存认证态：

```bash
poetry run python launch_camoufox.py --debug
```

登录成功后，确认 `auth_profiles/active/` 下已有可用 `.json` 文件。后续可切换为无头模式。

## 5. 日常运行

```bash
poetry run python launch_camoufox.py --headless
```

Linux 无桌面环境可选：

```bash
poetry run python launch_camoufox.py --virtual-display
```

## 6. 最小可用验证

```bash
# 健康检查
curl http://127.0.0.1:2048/health

# 模型列表
curl http://127.0.0.1:2048/v1/models

# 聊天补全
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-pro","messages":[{"role":"user","content":"你好"}]}'
```

## 7. Docker 快速路径（已有认证文件时）

1. 确保宿主机已有 `auth_profiles/active/*.json`。
2. 进入 Docker 目录并准备配置：

```bash
cd docker
cp .env.docker .env
```

3. 启动：

```bash
docker compose up -d --build
```

4. 检查：

```bash
docker compose ps
docker compose logs -f
```

> 详细部署、更新与排障见 `docs/deployment-and-operations.md`。
