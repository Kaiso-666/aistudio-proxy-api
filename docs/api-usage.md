# API 使用说明

## 1. 核心 OpenAI 兼容接口

## 1.1 健康检查

```bash
curl http://127.0.0.1:2048/health
```

返回 `200` 表示核心状态正常；`503` 时请关注 `details` 字段中的 browser/page/worker 状态。

## 1.2 模型列表

```bash
curl http://127.0.0.1:2048/v1/models
```

## 1.3 聊天补全（非流式）

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"gemini-2.5-pro",
    "messages":[{"role":"user","content":"请总结今天的任务"}],
    "temperature":0.8
  }'
```

## 1.4 聊天补全（流式）

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"gemini-2.5-pro",
    "stream":true,
    "messages":[{"role":"user","content":"写一段 100 字短文"}]
  }' --no-buffer
```

---

## 2. API Key 鉴权

当密钥文件中存在有效 key 时，`/v1/*`（除公开白名单）将开启鉴权。

支持两种请求头：

- `Authorization: Bearer <token>`（推荐）
- `X-API-Key: <token>`（兼容）

管理接口：

- `GET /api/keys`：查询密钥
- `POST /api/keys`：新增密钥
- `POST /api/keys/test`：测试密钥
- `DELETE /api/keys`：删除密钥

---

## 3. 队列与请求控制

- `GET /v1/queue`：查看排队请求、等待时长、是否被取消
- `POST /v1/cancel/{req_id}`：取消排队中的请求

示例：

```bash
curl http://127.0.0.1:2048/v1/queue
curl -X POST http://127.0.0.1:2048/v1/cancel/abc1234
```

---

## 4. 服务端管理接口（Web UI 同源使用）

- `GET /api/info`
- `GET /api/server/status`
- `POST /api/server/restart`
- `GET/POST /api/proxy/config`
- `POST /api/proxy/test`
- `GET/POST /api/helper/config`
- `GET/POST /api/ports/config`
- `GET /api/ports/status`
- `POST /api/ports/kill`
- `GET /api/auth/files`
- `GET /api/auth/active`
- `POST /api/auth/activate`
- `DELETE /api/auth/deactivate`
- `GET /api/model-capabilities`
- `GET /api/model-capabilities/{model_id}`
- `WS /ws/logs`

> 这些接口主要为内置管理 UI 服务；若你要对外暴露，请在网关层做访问控制。

