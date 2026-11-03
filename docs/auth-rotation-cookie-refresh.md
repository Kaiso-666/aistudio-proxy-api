# 认证轮转与 Cookie 刷新

## 1. 目录角色

- `auth_profiles/active/`：当前生效认证（运行时读取）
- `auth_profiles/saved/`：可切换认证池
- `auth_profiles/emergency/`：应急认证池

通常建议：

1. 先在 debug 下登录并沉淀多个可用账号到 `saved/`
2. 生产运行时确保 `active/` 始终至少有一个可用 profile

## 2. 推荐上线流程

1. `--debug` 完成登录。
2. 验证 `/v1/models`、`/v1/chat/completions` 正常。
3. 将稳定账号纳入 `saved/` 池。
4. 切换 `--headless` 长期运行。

## 3. 自动轮转策略

关键配置：

- `AUTO_ROTATE_AUTH_PROFILE=true`
- `AUTO_AUTH_ROTATION_ON_STARTUP=true|false`
- `QUOTA_SOFT_LIMIT`：软阈值（倾向“当前请求结束后轮转”）
- `QUOTA_HARD_LIMIT`：硬阈值（触发更强恢复策略）
- `QUOTA_LIMIT_<MODEL_ID>`：模型粒度阈值

## 4. Cookie 自动刷新

建议长期运行时开启：

- `COOKIE_REFRESH_ENABLED=true`
- `COOKIE_REFRESH_INTERVAL_SECONDS=1800`
- `COOKIE_REFRESH_ON_REQUEST_ENABLED=true`
- `COOKIE_REFRESH_REQUEST_INTERVAL=10`
- `COOKIE_REFRESH_ON_SHUTDOWN=true`

效果：

- 降低长期运行下 cookie 过期风险
- 关停前自动落盘，减少重启失效

## 5. 管理接口（便于运维）

- `GET /api/auth/files`：列出 saved 文件与当前 active
- `POST /api/auth/activate`：切换某个认证文件为 active
- `DELETE /api/auth/deactivate`：清空 active

