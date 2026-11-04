import asyncio
from typing import Any, Dict, List, Optional, Union

from api_utils.tools_registry import execute_tool_call, register_runtime_tools
from api_utils.utils_ext.string_utils import (
    extract_json_from_text,
    get_latest_user_text,
)
from models import Message


async def maybe_execute_tools(
    messages: List[Message],
    tools: Optional[List[Dict[str, Any]]],
    tool_choice: Optional[Union[str, Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """
    Actively execute a tool only when that is unambiguous and actually possible.

    - A named function (string or {type:'function', function:{name}}) is
      executed only if this server has a real handler for it.
    - 'auto' / 'required' / 'any' never execute here: they delegate the choice
      of function *and* its arguments to the model. Executing a single declared
      tool under 'auto' used to skip the model entirely and return a fabricated
      call whose arguments were scraped from the user's text - in practice
      always "{}", which breaks every agent that sends one tool at a time.
    - Returns [{name, arguments, result}]; None when nothing should run here.
    """
    try:
        # Track runtime-declared tools and optional MCP endpoints
        mcp_ep: Optional[str] = None
        # support per-request MCP endpoint via request-level message or tool spec extension (if present later)
        # current: read from env only in registry when not provided
        register_runtime_tools(tools, mcp_ep)
        # If tool result messages already exist (role='tool'), follow the conversational calling loop,
        # driven by the client, the server does not actively execute again.
        for m in messages:
            if getattr(m, "role", None) == "tool":
                return None
        chosen_name: Optional[str] = None
        if isinstance(tool_choice, dict):
            fn_raw = tool_choice.get("function")
            if isinstance(fn_raw, dict):
                name_raw = fn_raw.get("name")
                if isinstance(name_raw, str):
                    chosen_name = name_raw
        elif isinstance(tool_choice, str):
            lc = tool_choice.lower()
            if lc in ("none", "no", "off", "auto", "required", "any"):
                return None
            else:
                chosen_name = tool_choice
        elif tool_choice is None:
            # Do not execute actively
            return None

        if not chosen_name:
            return None

        from api_utils.tools_registry import can_execute_locally

        if not can_execute_locally(chosen_name):
            # Declared by the client, not executable here. Let the model emit
            # the call with real arguments instead of fabricating "{}".
            return None

        user_text = get_latest_user_text(messages)
        args_json = extract_json_from_text(user_text) or "{}"
        result_str = await execute_tool_call(chosen_name, args_json)
        return [{"name": chosen_name, "arguments": args_json, "result": result_str}]
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
