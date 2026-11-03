# 配置参考

配置文件入口：项目根目录 `.env`（可由 `.env.example` 复制）。

> 说明：下表“默认值”以 `.env.example` 为主；若未设置，代码里也有兜底值，少数项可能不同（例如 `FUNCTION_CALLING_MODE`）。

## 1. 网络与端口

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `2048` | FastAPI 主服务端口。 |
| `STREAM_PORT` | `3120` | 流代理端口；`0` 表示关闭流代理。 |
| `DEFAULT_FASTAPI_PORT` | `2048` | 启动器默认端口（UI/CLI 提示用）。 |
| `DEFAULT_CAMOUFOX_PORT` | `9222` | 启动器默认 Camoufox 调试端口。 |
| `UNIFIED_PROXY_CONFIG` | 空 | 统一代理入口，优先级高于 HTTP/HTTPS 代理。 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 空 | 兼容代理配置。 |
| `NO_PROXY` | 空 | 代理绕过规则。 |

## 2. 启动与浏览器

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `LAUNCH_MODE` | `normal` | 启动模式：`normal/debug/headless/virtual_display/direct_debug_no_browser`。 |
| `CAMOUFOX_WS_ENDPOINT` | 空 | 外部浏览器 WebSocket 地址；常规启动时由 launcher 注入。 |
| `DIRECT_LAUNCH` | `false` | 跳过菜单直接按配置启动。 |
| `ENDPOINT_CAPTURE_TIMEOUT` | `45` | 捕获浏览器 ws 端点超时时间（秒）。 |
| `ONLY_COLLECT_CURRENT_USER_ATTACHMENTS` | `false` | 限制附件收集范围。 |

## 3. 认证、轮转、Cookie 刷新

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTO_SAVE_AUTH` | `false` | Debug 登录成功后自动保存认证。 |
| `AUTH_SAVE_TIMEOUT` | `30` | 保存认证等待超时（秒）。 |
| `AUTO_ROTATE_AUTH_PROFILE` | `true` | 配额/异常时自动轮转认证。 |
| `AUTO_AUTH_ROTATION_ON_STARTUP` | `false` | 启动时自动选取可用 profile。 |
| `AUTO_CONFIRM_LOGIN` | `true` | 自动确认登录流程。 |
| `QUOTA_SOFT_LIMIT` | `850000` | 软阈值（请求完成后轮转）。 |
| `QUOTA_HARD_LIMIT` | `950000` | 硬阈值（更强保护/更快触发恢复）。 |
| `QUOTA_LIMIT_<MODEL_ID>` | 空 | 某模型的专属阈值（高级用法）。 |
| `COOKIE_REFRESH_ENABLED` | `true` | 启用周期性 cookie 刷新。 |
| `COOKIE_REFRESH_INTERVAL_SECONDS` | `1800` | 周期刷新间隔（秒）。 |
| `COOKIE_REFRESH_ON_REQUEST_ENABLED` | `true` | 按请求计数触发刷新。 |
| `COOKIE_REFRESH_REQUEST_INTERVAL` | `10` | 每成功 N 次请求触发保存。 |
| `COOKIE_REFRESH_ON_SHUTDOWN` | `true` | 优雅关停时保存 cookie。 |

## 4. API 默认采样与能力开关

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `DEFAULT_TEMPERATURE` | `1.0` | 默认温度。 |
| `DEFAULT_MAX_OUTPUT_TOKENS` | `65536` | 默认输出 token 上限。 |
| `DEFAULT_TOP_P` | `0.95` | 默认 `top_p`。 |
| `DEFAULT_STOP_SEQUENCES` | `["User:"]` | 默认停用序列（JSON 字符串）。 |
| `ENABLE_THINKING_BUDGET` | `true` | 启用 thinking budget。 |
| `DEFAULT_THINKING_BUDGET` | `8192` | 默认 thinking budget。 |
| `THINKING_BUDGET_LOW/MEDIUM/HIGH` | `10923/21845/32768` | 分级预算。 |
| `DEFAULT_THINKING_LEVEL_PRO` | `high` | Pro 系列默认思考等级。 |
| `DEFAULT_THINKING_LEVEL_FLASH` | `high` | Flash 系列默认思考等级。 |
| `DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE` | `false` | 关闭 stream 时是否自动关闭 thinking budget。 |
| `ENABLE_GOOGLE_SEARCH` | `false` | 开启 Google Search 能力映射。 |
| `ENABLE_URL_CONTEXT` | `false` | 开启 URL Context 能力映射。 |

## 5. Function Calling（核心）

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `FUNCTION_CALLING_MODE` | `.env` 为 `auto` | 模式：`auto/native/emulated`（代码兜底为 `emulated`）。 |
| `FUNCTION_CALLING_NATIVE_FALLBACK` | `true` | native 失败后回退 emulated。 |
| `FUNCTION_CALLING_UI_TIMEOUT` | `10000` | UI 操作超时（毫秒）。 |
| `FUNCTION_CALLING_NATIVE_RETRY_COUNT` | `3` | native 重试次数。 |
| `FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS` | `true` | 请求间是否清理函数定义。 |
| `FUNCTION_CALLING_CACHE_ENABLED` | `true` | 开启 FC 状态缓存。 |
| `FUNCTION_CALLING_CACHE_TTL` | `0` | 缓存 TTL（0 表示会话内不过期）。 |
| `FUNCTION_CALLING_THOUGHT_SIGNATURE` | `true` | Gemini 3 兼容字段。 |
| `FUNCTION_CALLING_UPPERCASE_TYPES` | `false` | schema type 大写兼容模式。 |

调试相关：

- `FUNCTION_CALLING_DEBUG`
- `FC_DEBUG_*`（模块开关、级别、截断、合并日志）

## 6. 日志与诊断

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `SERVER_LOG_LEVEL` | `INFO` | 主日志级别。 |
| `SERVER_REDIRECT_PRINT` | `false` | 是否将 `print` 重定向到日志。 |
| `DEBUG_LOGS_ENABLED` | `false` | DEBUG 级日志总开关。 |
| `TRACE_LOGS_ENABLED` | `false` | TRACE 级日志总开关。 |
| `JSON_LOGS` | `false` | JSON 结构化日志。 |
| `LOG_FILE_MAX_BYTES` | `10485760` | 日志切割大小。 |
| `LOG_FILE_BACKUP_COUNT` | `5` | 滚动日志保留份数。 |

## 7. 超时与稳态参数

常用项（按需调优）：

- `RESPONSE_COMPLETION_TIMEOUT`
- `SILENCE_TIMEOUT_MS`
- `CLICK_TIMEOUT_MS`
- `WAIT_FOR_ELEMENT_TIMEOUT_MS`
- `STREAM_MAX_INITIAL_ERRORS`
- `STREAM_WARNING_INTERVAL_AFTER_SUPPRESS`
- `STREAM_SUPPRESS_DURATION_AFTER_INITIAL_BURST`

## 8. GUI 相关

仅 GUI 启动器会使用：

- `GUI_DEFAULT_PROXY_ADDRESS`
- `GUI_DEFAULT_STREAM_PORT`
- `GUI_DEFAULT_HELPER_ENDPOINT`
- `SKIP_FRONTEND_BUILD`

