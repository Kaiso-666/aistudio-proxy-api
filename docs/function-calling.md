# 函数调用模式

本项目支持 OpenAI 风格 `tools/tool_calls`，并提供三种模式：

- `auto`：优先 native，失败自动回退 emulated（推荐）
- `native`：完全依赖 AI Studio 原生函数调用 UI
- `emulated`：文本注入方式，兼容旧流程

## 关键配置

- `FUNCTION_CALLING_MODE`
- `FUNCTION_CALLING_NATIVE_FALLBACK`
- `FUNCTION_CALLING_UI_TIMEOUT`
- `FUNCTION_CALLING_NATIVE_RETRY_COUNT`
- `FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS`

## 缓存与调试

- `FUNCTION_CALLING_CACHE_ENABLED`
- `FUNCTION_CALLING_CACHE_TTL`
- `FUNCTION_CALLING_DEBUG`
- `FC_DEBUG_*`（模块级日志）

## 兼容增强

- `FUNCTION_CALLING_THOUGHT_SIGNATURE`
- `FUNCTION_CALLING_UPPERCASE_TYPES`

> 建议默认保持 `THOUGHT_SIGNATURE=true`、`UPPERCASE_TYPES=false`，除非你已验证目标 UI 行为。
