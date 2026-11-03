# Function Calling Improvements

本文件说明 `.env` 中 FC-001 ~ FC-004 相关配置的设计目的。

## FC-001 `FUNCTION_CALLING_THOUGHT_SIGNATURE`

为 Gemini 3 系列模型在函数调用回放时补齐 `thoughtSignature`，降低校验失败概率。

## FC-004 `FUNCTION_CALLING_UPPERCASE_TYPES`

可选地将 JSON Schema 类型转换为大写（如 `string -> STRING`）。
默认关闭，建议仅在目标 UI 验证通过后启用。

## 建议默认值

- `FUNCTION_CALLING_THOUGHT_SIGNATURE=true`
- `FUNCTION_CALLING_UPPERCASE_TYPES=false`
