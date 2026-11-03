# 排障指南

## 1. 启动阶段失败

### 现象 A：浏览器相关初始化失败

优先检查：

1. `CAMOUFOX_WS_ENDPOINT` 是否被 launcher 正确注入（或你是否手动提供了有效地址）
2. 网络与代理配置（`UNIFIED_PROXY_CONFIG`）
3. 是否已有可用认证文件（`auth_profiles/active/*.json`）

### 现象 B：`/health` 一直是 503

查看响应中的 `details`：

- `is_playwright_ready`
- `is_browser_connected`
- `is_page_ready`
- `workerRunning`

如果 `launchMode=direct_debug_no_browser`，browser/page 不是硬依赖。

---

## 2. 聊天接口超时或挂起

### 排查步骤

1. 检查请求是否持续积压：`GET /v1/queue`
2. 查看日志中的 timeout/silence 关键字
3. 调整超时参数：
   - `RESPONSE_COMPLETION_TIMEOUT`
   - `SILENCE_TIMEOUT_MS`
   - `WAIT_FOR_ELEMENT_TIMEOUT_MS`
4. 在 debug 模式观察 AI Studio 页面是否卡住

---

## 3. Function Calling 异常

建议顺序：

1. `FUNCTION_CALLING_MODE=auto`
2. 开启 `FUNCTION_CALLING_DEBUG=true`
3. 仅打开必要 `FC_DEBUG_*` 模块（先 `ORCHESTRATOR/UI/WIRE`）
4. 观察 `logs/fc_debug/` 具体报错

如是 UI 结构变化导致，可核查 `config/selectors.py` 相关选择器。

---

## 4. 认证轮转不生效 / 频繁触发

检查：

- `AUTO_ROTATE_AUTH_PROFILE`
- `AUTO_AUTH_ROTATION_ON_STARTUP`
- `QUOTA_SOFT_LIMIT` / `QUOTA_HARD_LIMIT`
- `saved/` 或 `emergency/` 是否有可用 profile

如果“轮转后仍很快触发”，优先确认账号是否都已接近配额。

---

## 5. Docker 常见问题

### 认证文件问题

容器无头运行时不能完成交互登录。必须先在宿主机生成认证文件，再挂载 `auth_profiles/`。

### 健康检查失败

```bash
docker compose logs -f
docker compose exec ai-studio-proxy /bin/bash
curl -v http://127.0.0.1:2048/health
```

### 日志/权限问题

如果你挂载了 `../logs:/app/logs`，需保证目录可写。

