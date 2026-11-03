# FC Debug Logging Design

函数调用调试日志采用“总开关 + 模块开关”模式：

- 总开关：`FUNCTION_CALLING_DEBUG`
- 模块开关：`FC_DEBUG_ORCHESTRATOR/UI/CACHE/WIRE/DOM/SCHEMA/RESPONSE`
- 轮转策略：`FC_DEBUG_LOG_MAX_BYTES` + `FC_DEBUG_LOG_BACKUP_COUNT`
- 截断策略：`FC_DEBUG_TRUNCATE_*`

日志目录：`logs/fc_debug/`。
