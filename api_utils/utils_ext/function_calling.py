"""
Function Calling Utilities for Native Function Calling Support.

This module provides:
- Schema conversion from OpenAI tools format to Gemini FunctionDeclaration format
- Call ID generation and management for tracking tool calls
- Response formatting from Gemini responses to OpenAI tool_calls format

Implements Phase 1 of ADR-001: Native Function Calling Architecture.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from config.settings import FUNCTION_CALLING_DEBUG
from logging_utils.fc_debug import FCModule, get_fc_logger

logger = logging.getLogger("AIStudioProxyServer")

# FC debug logger for schema conversion and response formatting
fc_logger = get_fc_logger()


# =============================================================================
# Constants for Function Calling Improvements
# =============================================================================

# Constant signature value used for Gemini 3 function call validation
# This is a placeholder that satisfies the API validation requirement
# Reference: iBUHub/AIStudioToAPI FormatConverter.js lines 84-112
DUMMY_THOUGHT_SIGNATURE: str = "context_engineering_is_the_way_to_go"

# Type mappings for schema conversion - UPPERCASE variant (pending UI verification)
TYPE_MAP_UPPER: Dict[str, str] = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
    "null": "NULL",
}

# Type mappings for schema conversion - lowercase variant (current, verified working)
TYPE_MAP_LOWER: Dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
    "null": "null",
}

# Type alias for MCP response items
MCPResponseItem = Dict[str, Any]


# =============================================================================
# Configuration Types
# =============================================================================


class FunctionCallingMode(str, Enum):
    """Function calling mode selection.

    - EMULATED: Current text-based approach (default, backwards compatible)
    - NATIVE: AI Studio UI-driven function calling
    - AUTO: Native with automatic fallback to emulated on failure
    """

    EMULATED = "emulated"
    NATIVE = "native"
    AUTO = "auto"


@dataclass
class FunctionCallingConfig:
    """Configuration for function calling behavior.

    Attributes:
        mode: The function calling mode to use.
        native_fallback: Whether to fallback to emulated mode on native failure.
        ui_timeout_ms: Timeout for UI operations in milliseconds.
        native_retry_count: Number of retries for native mode UI operations.
        clear_between_requests: Whether to clear function definitions between requests.
        debug: Enable detailed debug logging.
    """

    mode: FunctionCallingMode = FunctionCallingMode.EMULATED
    native_fallback: bool = True
    ui_timeout_ms: int = 5000
    native_retry_count: int = 2
    clear_between_requests: bool = True
    debug: bool = False

    @classmethod
    def from_settings(cls) -> "FunctionCallingConfig":
        """Create configuration from environment settings."""
        from config.settings import (
            FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS,
            FUNCTION_CALLING_DEBUG,
            FUNCTION_CALLING_MODE,
            FUNCTION_CALLING_NATIVE_FALLBACK,
            FUNCTION_CALLING_NATIVE_RETRY_COUNT,
            FUNCTION_CALLING_UI_TIMEOUT,
        )

        mode_str = FUNCTION_CALLING_MODE.lower()
        try:
            mode = FunctionCallingMode(mode_str)
        except ValueError:
            mode = FunctionCallingMode.EMULATED

        return cls(
            mode=mode,
            native_fallback=FUNCTION_CALLING_NATIVE_FALLBACK,
            ui_timeout_ms=FUNCTION_CALLING_UI_TIMEOUT,
            native_retry_count=FUNCTION_CALLING_NATIVE_RETRY_COUNT,
            clear_between_requests=FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS,
            debug=FUNCTION_CALLING_DEBUG,
        )


# =============================================================================
# Tool Choice Conversion: OpenAI -> Gemini (FC-003)
# =============================================================================


@dataclass
class GeminiToolConfig:
    """Gemini API toolConfig.functionCallingConfig structure.

    NOTE: This config is for logging/future API mode only.
    Current UI automation does not support applying this config.

    Represents the Gemini-native way to control function calling behavior.

    Attributes:
        mode: Function calling mode. One of:
              - "AUTO": Model decides whether to call functions
              - "NONE": Model must not call functions
              - "ANY": Model must call at least one function
        allowed_function_names: Optional list of function names the model is
                                allowed to call. Only valid with mode="ANY".
    """

    mode: str
    allowed_function_names: Optional[List[str]] = None

    # Valid mode values
    VALID_MODES = frozenset({"AUTO", "NONE", "ANY"})

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid mode: {self.mode}. Must be one of {self.VALID_MODES}"
            )

        if self.allowed_function_names is not None and self.mode != "ANY":
            raise ValueError(
                f"allowed_function_names is only valid with mode='ANY', "
                f"got mode='{self.mode}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Gemini API request format.

        Returns:
            Dict suitable for inclusion in toolConfig field of Gemini request.

        Example:
            >>> config = GeminiToolConfig(mode="ANY", allowed_function_names=["fn1"])
            >>> config.to_dict()
            {'functionCallingConfig': {'mode': 'ANY', 'allowedFunctionNames': ['fn1']}}
        """
        config: Dict[str, Any] = {"mode": self.mode}

        if self.allowed_function_names:
            config["allowedFunctionNames"] = self.allowed_function_names

        return {"functionCallingConfig": config}

    def __str__(self) -> str:
        """Human-readable representation for logging."""
        if self.allowed_function_names:
            funcs = ", ".join(self.allowed_function_names)
            return f"GeminiToolConfig(mode={self.mode}, functions=[{funcs}])"
        return f"GeminiToolConfig(mode={self.mode})"

    def __repr__(self) -> str:
        return (
            f"GeminiToolConfig(mode={self.mode!r}, "
            f"allowed_function_names={self.allowed_function_names!r})"
        )


def convert_tool_choice(
    tool_choice: Union[str, Dict[str, Any], None],
) -> Optional[GeminiToolConfig]:
    """Convert OpenAI tool_choice parameter to Gemini toolConfig.

    OpenAI to Gemini mapping:
    - "auto" -> mode: AUTO
    - "none" -> mode: NONE
    - "required" -> mode: ANY
    - {"type": "function", "function": {"name": "x"}} -> mode: ANY, allowedFunctionNames: ["x"]
    - "function_name" (string) -> mode: ANY, allowedFunctionNames: ["function_name"]

    NOTE: This conversion is for logging/future API use only.
    AI Studio UI automation CANNOT set toolConfig.

    Args:
        tool_choice: OpenAI tool_choice parameter. Can be:
                     - None: No preference
                     - str: "auto", "none", "required", or function name
                     - dict: Specific function selection

    Returns:
        GeminiToolConfig if tool_choice is specified and recognized,
        None if tool_choice is None or unrecognized.

    Examples:
        >>> convert_tool_choice("auto")
        GeminiToolConfig(mode='AUTO', allowed_function_names=None)

        >>> convert_tool_choice("required")
        GeminiToolConfig(mode='ANY', allowed_function_names=None)

        >>> convert_tool_choice({"type": "function", "function": {"name": "get_weather"}})
        GeminiToolConfig(mode='ANY', allowed_function_names=['get_weather'])
    """
    if tool_choice is None:
        return None

    # Handle string values
    if isinstance(tool_choice, str):
        choice_lower = tool_choice.lower().strip()

        if choice_lower == "auto":
            return GeminiToolConfig(mode="AUTO")
        elif choice_lower == "none":
            return GeminiToolConfig(mode="NONE")
        elif choice_lower == "required":
            return GeminiToolConfig(mode="ANY")
        else:
            # Treat as function name (some clients pass function name directly)
            return GeminiToolConfig(mode="ANY", allowed_function_names=[tool_choice])

    # Handle dict format
    if isinstance(tool_choice, dict):
        # Standard format: {"type": "function", "function": {"name": "x"}}
        function_spec = tool_choice.get("function")
        if isinstance(function_spec, dict):
            func_name = function_spec.get("name")
            if func_name and isinstance(func_name, str):
                return GeminiToolConfig(mode="ANY", allowed_function_names=[func_name])

        # Legacy format: {"name": "x"}
        func_name = tool_choice.get("name")
        if func_name and isinstance(func_name, str):
            return GeminiToolConfig(mode="ANY", allowed_function_names=[func_name])

    # Unrecognized format
    return None


# =============================================================================
# MCP Response Handling (FC-002)
# =============================================================================


def normalize_tool_response(
    content: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    preserve_on_error: bool = True,
) -> Dict[str, Any]:
    """Normalize various tool response formats to Gemini-compatible Struct.

    Gemini's functionResponse.response field requires a Struct (object),
    but MCP and other tool frameworks may return arrays or strings.
    This function normalizes all formats to valid Struct.

    Normalization rules:
    1. Dict input: returned as-is (already valid Struct)
    2. String input:
       - If valid JSON object: parsed and returned
       - Otherwise: wrapped as {"result": content}
    3. Array input:
       - Empty array: {"result": "[]"}
       - Single item with parseable JSON text: unwrapped to that object
       - Multiple items: wrapped as {"result": JSON.stringify(items)}

    Args:
        content: Tool response in any supported format.
        preserve_on_error: If True, wrap unparseable content rather than raising.

    Returns:
        Gemini-compatible response object (Struct).

    Raises:
        ValueError: If preserve_on_error=False and content cannot be normalized.

    Examples:
        >>> normalize_tool_response({"temp": 72})
        {'temp': 72}

        >>> normalize_tool_response("plain text")
        {'result': 'plain text'}

        >>> normalize_tool_response([{"type": "text", "text": '{"temp": 72}'}])
        {'temp': 72}
    """
    # Case 1: Already a dict - return as-is
    if isinstance(content, dict):
        return content

    # Case 2: String - try to parse as JSON object
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and parsed is not None:
                return parsed
            # Parsed but not a dict (array, primitive)
            return {"result": content}
        except (json.JSONDecodeError, TypeError):
            return {"result": content}

    # Case 3: Array (common in MCP)
    if isinstance(content, list):
        if len(content) == 0:
            return {"result": "[]"}

        processed_items: List[Any] = []

        for item in content:
            if not isinstance(item, dict):
                processed_items.append(item)
                continue

            # Handle MCP text items with nested JSON
            if item.get("type") == "text" and "text" in item:
                text_content = item["text"]
                try:
                    parsed = json.loads(text_content)
                    # Only unwrap if it's a proper dict
                    if isinstance(parsed, dict) and parsed is not None:
                        processed_items.append(parsed)
                    else:
                        # Keep as wrapped text for primitives/arrays
                        processed_items.append(
                            {"content": text_content, "type": "text"}
                        )
                except (json.JSONDecodeError, TypeError):
                    processed_items.append({"content": text_content, "type": "text"})
            else:
                # Keep other item types (image, etc.) as-is
                processed_items.append(item)

        # Unwrap single dict item
        if (
            len(processed_items) == 1
            and isinstance(processed_items[0], dict)
            and processed_items[0] is not None
        ):
            return processed_items[0]

        # Multiple items - wrap in result as JSON string
        try:
            return {"result": json.dumps(processed_items, ensure_ascii=False)}
        except (TypeError, ValueError):
            if preserve_on_error:
                return {"result": str(processed_items)}
            raise ValueError(f"Cannot serialize processed items: {processed_items}")

    # Fallback for other types
    if preserve_on_error:
        return {"result": str(content)}
    raise ValueError(f"Unsupported content type: {type(content)}")


# =============================================================================
# thoughtSignature Support for Gemini 3 (FC-001)
# =============================================================================


def ensure_thought_signature(
    messages: List[Dict[str, Any]],
    apply: bool = True,
    signature: str = DUMMY_THOUGHT_SIGNATURE,
) -> List[Dict[str, Any]]:
    """Add thoughtSignature to functionCall parts in conversation history.

    Gemini 3 models require thoughtSignature on functionCall parts when
    replaying conversation history. This function injects the signature
    into assistant messages that contain tool_calls.

    Rules:
    - Only assistant messages with tool_calls are modified
    - Only the FIRST tool_call in each message gets the signature
    - functionResponse (tool role) messages are NOT modified
    - Messages are cloned, original list is not mutated

    Args:
        messages: List of OpenAI-format message dicts.
        apply: If False, returns messages unchanged (for config toggle).
        signature: The signature value to inject.

    Returns:
        New list with thoughtSignature added where needed.
        Original messages list is not modified.

    Example:
        >>> messages = [
        ...     {"role": "user", "content": "What's the weather?"},
        ...     {"role": "assistant", "tool_calls": [
        ...         {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}
        ...     ]},
        ...     {"role": "tool", "tool_call_id": "call_1", "content": "Sunny"}
        ... ]
        >>> result = ensure_thought_signature(messages)
        >>> result[1]["tool_calls"][0]["_thought_signature"]
        'context_engineering_is_the_way_to_go'
    """
    if not apply:
        return messages

    if not messages:
        return messages

    result: List[Dict[str, Any]] = []

    for msg in messages:
        # Only process assistant messages with tool_calls
        if msg.get("role") != "assistant":
            result.append(msg)
            continue

        tool_calls = msg.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            result.append(msg)
            continue

        # Clone message to avoid mutation
        modified_msg = msg.copy()
        modified_calls: List[Dict[str, Any]] = []
        signature_added = False

        for call in tool_calls:
            if not isinstance(call, dict):
                modified_calls.append(call)
                continue

            call_copy = call.copy()

            # Add signature to first function-type call only
            if not signature_added and call.get("type") == "function":
                call_copy["_thought_signature"] = signature
                signature_added = True

            modified_calls.append(call_copy)

        modified_msg["tool_calls"] = modified_calls
        result.append(modified_msg)

    return result


# =============================================================================
# Schema Conversion: OpenAI -> Gemini
# =============================================================================


class SchemaConversionError(Exception):
    """Raised when schema conversion fails."""

    pass


class SchemaConverter:
    """Converts OpenAI tool definitions to Gemini FunctionDeclaration format.

    OpenAI Format:
    ```json
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            },
            "strict": true  # <-- Stripped (not supported)
        }
    }
    ```

    Gemini Format:
    ```json
    {
        "name": "get_weather",
        "description": "Get weather for a location",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    }
    ```
    """

    # =========================================================================
    # AI STUDIO SCHEMA WHITELIST (Empirically Tested)
    # =========================================================================
    # Only these fields are accepted by AI Studio's function calling UI.
    # This was tested against AI Studio web interface on 2025-12-24.
    #
    # IMPORTANT: AI Studio Web UI has STRICTER validation than the direct
    # Gemini API. The Gemini API docs list many fields that AI Studio rejects.
    #
    # -------------------------------------------------------------------------
    # SUPPORTED FIELDS (Tested & Working):
    # -------------------------------------------------------------------------
    ALLOWED_SCHEMA_FIELDS = {
        "type",  # Data type (REQUIRED on every property)
        "format",  # Format hint (e.g., "date-time", "email")
        "description",  # Human-readable description
        "nullable",  # Whether null is allowed
        "enum",  # Allowed values
        "maxItems",  # Maximum array items
        "minItems",  # Minimum array items
        "properties",  # Object properties
        "required",  # Required property names
        "items",  # Array item schema
        "minProperties",  # Minimum object properties
        "maxProperties",  # Maximum object properties
        "minimum",  # Minimum numeric value
        "maximum",  # Maximum numeric value
        "minLength",  # Minimum string length
        "maxLength",  # Maximum string length
        "pattern",  # Regex pattern for strings
        "propertyOrdering",  # Order of properties for display
    }

    # -------------------------------------------------------------------------
    # UNSUPPORTED FIELDS (AI Studio rejects these with "Unknown key" error):
    # -------------------------------------------------------------------------
    # DO NOT ADD THESE TO ALLOWED_SCHEMA_FIELDS - They have been tested and
    # confirmed to cause errors in AI Studio:
    #
    #   - "title"                : Unknown key error
    #   - "default"              : Unknown key error
    #   - "additionalProperties" : Unknown key error
    #   - "const"                : Unknown key error (convert to enum instead)
    #   - "anyOf"                : Unknown key error + "type must be specified"
    #   - "oneOf"                : Unknown key error (convert to first type)
    #   - "allOf"                : Unknown key error (convert to first type)
    #   - "$schema"              : Unknown key error
    #   - "$id"                  : Unknown key error
    #   - "$ref"                 : Unknown key error
    #   - "$defs"                : Unknown key error
    #   - "definitions"          : Unknown key error
    #   - "examples"             : Unknown key error
    #   - "exclusiveMinimum"     : Unknown key error
    #   - "exclusiveMaximum"     : Unknown key error
    #   - "multipleOf"           : Unknown key error
    #   - "uniqueItems"          : Unknown key error
    #   - "strict"               : OpenAI-specific, not supported
    #
    # =========================================================================

    # Fields that require special handling (recursion, conversion)
    # anyOf/oneOf/allOf are converted to first non-null type since AI Studio
    # doesn't support union types
    SPECIAL_FIELDS = {"type", "properties", "items", "anyOf", "const", "oneOf", "allOf"}

    # Legacy TYPE_MAP - kept for backwards compatibility
    # Use type_map property for configurable case
    TYPE_MAP = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }

    @property
    def type_map(self) -> Dict[str, str]:
        """Get the type map based on configuration.

        Returns:
            TYPE_MAP_UPPER if FUNCTION_CALLING_UPPERCASE_TYPES is True,
            TYPE_MAP_LOWER otherwise.

        This allows configurable type case for Gemini compatibility.
        Default is lowercase (TYPE_MAP_LOWER) for backwards compatibility.
        """
        from config.settings import FUNCTION_CALLING_UPPERCASE_TYPES

        return TYPE_MAP_UPPER if FUNCTION_CALLING_UPPERCASE_TYPES else TYPE_MAP_LOWER

    def _normalize_type(self, type_value: str) -> str:
        """Normalize a type value using the configured type map.

        Args:
            type_value: JSON Schema type string (e.g., "string", "object").

        Returns:
            Normalized type string based on configuration.
        """
        lower_type = type_value.lower().strip()
        current_type_map = self.type_map
        # If not in map, use the configured case convention
        from config.settings import FUNCTION_CALLING_UPPERCASE_TYPES

        default = lower_type.upper() if FUNCTION_CALLING_UPPERCASE_TYPES else lower_type
        return current_type_map.get(lower_type, default)

    def convert_tool(self, openai_tool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a single OpenAI tool definition to Gemini FunctionDeclaration.

        Supports both standard OpenAI format and flat format (e.g. from opencode).
        Safely ignores non-function tools.

        Args:
            openai_tool: OpenAI tool definition.

        Returns:
            Gemini FunctionDeclaration dict, or None if the tool should be ignored.

        Raises:
            SchemaConversionError: If the tool is a function but the format is invalid.
        """
        if not isinstance(openai_tool, dict):
            return None

        tool_type = openai_tool.get("type")
        if tool_type != "function":
            if FUNCTION_CALLING_DEBUG:
                logger.debug(f"Ignoring non-function tool type: {tool_type}")
            return None

        # Try to find function definition (nested or flat)
        function_def = openai_tool.get("function")
        if isinstance(function_def, dict):
            # Standard format: {"type": "function", "function": {"name": "...", ...}}
            source = function_def
        else:
            # Maybe flat format: {"type": "function", "name": "...", "parameters": { ... }}
            source = openai_tool

        name = source.get("name")
        if not name or not isinstance(name, str):
            raise SchemaConversionError(
                "Function 'name' is required and must be a string"
            )

        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Converting OpenAI tool to Gemini: {name}")
            fc_logger.debug(FCModule.SCHEMA, f"Converting tool: {name}")

        # Build Gemini FunctionDeclaration
        gemini_declaration: Dict[str, Any] = {"name": name}

        # Description is optional but recommended
        description = source.get("description")
        if description and isinstance(description, str):
            gemini_declaration["description"] = description

        # Parameters are optional (some functions have no params)
        parameters = source.get("parameters")
        if parameters and isinstance(parameters, dict):
            # Strip unsupported fields but keep the rest
            clean_params = self._clean_parameters(parameters)
            gemini_declaration["parameters"] = clean_params

        if FUNCTION_CALLING_DEBUG:
            logger.debug(
                f"Converted tool '{name}' to Gemini format: {json.dumps(gemini_declaration, ensure_ascii=False)}"
            )

        return gemini_declaration

    def convert_tools(self, openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert an array of OpenAI tool definitions to Gemini FunctionDeclarations.

        Args:
            openai_tools: List of OpenAI tool definitions.

        Returns:
            List of Gemini FunctionDeclaration dicts.

        Raises:
            SchemaConversionError: If any tool conversion fails or tools is not a list.
        """
        if not isinstance(openai_tools, list):
            raise SchemaConversionError(
                f"Tools must be a list, got {type(openai_tools).__name__}"
            )

        declarations: List[Dict[str, Any]] = []
        for i, tool in enumerate(openai_tools):
            try:
                declaration = self.convert_tool(tool)
                if declaration:
                    declarations.append(declaration)
            except SchemaConversionError as e:
                raise SchemaConversionError(f"Error converting tool at index {i}: {e}")

        if FUNCTION_CALLING_DEBUG:
            fc_logger.info(
                FCModule.SCHEMA,
                f"Converted {len(declarations)} tools to Gemini format",
            )
        return declarations

    def to_json_string(
        self, declarations: List[Dict[str, Any]], indent: Optional[int] = 2
    ) -> str:
        """Serialize Gemini FunctionDeclarations to JSON string for UI paste.

        Args:
            declarations: List of Gemini FunctionDeclaration dicts.
            indent: JSON indentation (None for compact, int for pretty).

        Returns:
            JSON string suitable for pasting into AI Studio function declarations textarea.
        """
        return json.dumps(declarations, indent=indent, ensure_ascii=False)

    def _clean_parameters(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert OpenAI/JSON Schema to Gemini-compatible format.

        Uses WHITELIST approach - only copies fields that Gemini/AI Studio accepts.
        AI Studio rejects unknown fields with errors like "Unknown key 'additionalProperties'".

        Handles:
        - Type normalization (list to single type + nullable)
        - Conversion: const -> enum, oneOf/allOf -> anyOf (simplified)
        - Whitelist-based field filtering
        - Recursive cleaning of nested schemas
        """
        if not isinstance(schema, dict):
            return schema

        cleaned: Dict[str, Any] = {}

        # 1. Handle anyOf/oneOf/allOf: AI Studio doesn't support these, extract first non-null type
        for logic_field in ["anyOf", "oneOf", "allOf"]:
            if logic_field in schema:
                val = schema[logic_field]
                if isinstance(val, list) and len(val) > 0:
                    # Find the first non-null option and use it
                    for option in val:
                        if isinstance(option, dict):
                            option_type = option.get("type")
                            if option_type != "null":
                                # Merge the first valid option into cleaned
                                merged = self._clean_parameters(option)
                                cleaned.update(merged)
                                break
                    # Check if null was an option for nullable
                    for option in val:
                        if isinstance(option, dict) and option.get("type") == "null":
                            cleaned["nullable"] = True
                            break
                    # Return early since logic fields define the whole schema
                    if cleaned:
                        return cleaned

        # 2. Handle Const Conversion: const -> enum
        if "const" in schema:
            cleaned["enum"] = [schema["const"]]

        # 3. Handle Type Normalization: ["string", "null"] -> "string" + nullable
        if "type" in schema:
            raw_type = schema["type"]
            nullable = schema.get("nullable", False)

            if isinstance(raw_type, list):
                if "null" in raw_type:
                    nullable = True
                # Get the first non-null type
                types = [t for t in raw_type if t != "null"]
                raw_type = types[0] if types else "string"

            if nullable:
                cleaned["nullable"] = True

            # Map type using configurable type map
            if isinstance(raw_type, str):
                cleaned["type"] = self._normalize_type(raw_type)

        # 4. Handle properties recursively (must do before the loop)
        if "properties" in schema and isinstance(schema["properties"], dict):
            cleaned["properties"] = {
                prop_name: self._clean_parameters(prop_schema)
                for prop_name, prop_schema in schema["properties"].items()
            }

        # 5. Handle items recursively (for arrays)
        if "items" in schema and isinstance(schema["items"], dict):
            cleaned["items"] = self._clean_parameters(schema["items"])

        # 6. Copy ONLY allowed fields (whitelist approach)
        for key, value in schema.items():
            # Skip fields we already handled
            if key in self.SPECIAL_FIELDS:
                continue

            # Skip nullable if already set from type array
            if key == "nullable" and "nullable" in cleaned:
                continue

            # Only copy fields that Gemini accepts
            if key not in self.ALLOWED_SCHEMA_FIELDS:
                continue

            # Copy allowed fields as-is (properties/items already handled above)
            if key not in cleaned:
                cleaned[key] = value

        return cleaned


# =============================================================================
# Call ID Manager
# =============================================================================


@dataclass
class PendingCall:
    """Represents a pending function call awaiting result.

    Attributes:
        call_id: Unique identifier for this call (call_<uuid>).
        function_name: Name of the function being called.
        arguments: Arguments passed to the function.
        timestamp: Unix timestamp when the call was registered.
    """

    call_id: str
    function_name: str
    arguments: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class CallIdManager:
    """Generates and tracks function call IDs.

    Gemini does not return call IDs, so the proxy must generate and track them
    to maintain OpenAI API compatibility.

    ID Format: call_<24-character-hex>
    Example: call_a1b2c3d4e5f6789012345678
    """

    # Prefix for all generated call IDs
    CALL_ID_PREFIX = "call_"
    # Length of the hex portion of the ID
    HEX_LENGTH = 24

    def __init__(self) -> None:
        """Initialize the call ID manager."""
        self._pending_calls: Dict[str, PendingCall] = {}

    def generate_id(self) -> str:
        """Generate a unique call ID.

        Returns:
            A unique call ID in format: call_<24-character-hex>
        """
        hex_part = uuid.uuid4().hex[: self.HEX_LENGTH]
        return f"{self.CALL_ID_PREFIX}{hex_part}"

    def register_call(
        self,
        call_id: str,
        function_name: str,
        arguments: Dict[str, Any],
    ) -> PendingCall:
        """Register a function call for tracking.

        Args:
            call_id: The unique call ID.
            function_name: Name of the function being called.
            arguments: Arguments for the function call.

        Returns:
            The registered PendingCall object.
        """
        pending = PendingCall(
            call_id=call_id,
            function_name=function_name,
            arguments=arguments,
        )
        self._pending_calls[call_id] = pending
        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Registered pending call: {call_id} -> {function_name}")
        return pending

    def get_pending_call(self, call_id: str) -> Optional[PendingCall]:
        """Get a pending call by ID.

        Args:
            call_id: The call ID to look up.

        Returns:
            The PendingCall if found, None otherwise.
        """
        return self._pending_calls.get(call_id)

    def get_pending_calls(self) -> List[PendingCall]:
        """Get all pending calls.

        Returns:
            List of all pending calls.
        """
        return list(self._pending_calls.values())

    def remove_call(self, call_id: str) -> Optional[PendingCall]:
        """Remove a pending call (when result is received).

        Args:
            call_id: The call ID to remove.

        Returns:
            The removed PendingCall if found, None otherwise.
        """
        return self._pending_calls.pop(call_id, None)

    def clear(self) -> None:
        """Clear all pending calls."""
        self._pending_calls.clear()


# =============================================================================
# Parsed Function Call Types
# =============================================================================


@dataclass
class ParsedFunctionCall:
    """Represents a parsed function call from Gemini's response.

    Attributes:
        name: The function name.
        arguments: Parsed arguments as a dict (not string).
        raw_text: Original raw text if parsed from text (for debugging).
    """

    name: str
    arguments: Dict[str, Any]
    raw_text: Optional[str] = None


# =============================================================================
# Response Formatter: Gemini -> OpenAI
# =============================================================================


class OpenAIFunctionCall(BaseModel):
    """OpenAI function call structure within a tool call."""

    name: str
    arguments: str  # JSON string, NOT dict


class OpenAIToolCall(BaseModel):
    """OpenAI tool_calls array item structure."""

    id: str
    type: str = "function"
    function: OpenAIFunctionCall


class OpenAIToolCallDelta(BaseModel):
    """OpenAI streaming delta for tool calls."""

    index: int
    id: Optional[str] = None  # Only on first chunk
    type: Optional[str] = None  # Only on first chunk
    function: Optional[Dict[str, Any]] = None  # Contains name and/or arguments


class ResponseFormatter:
    """Formats parsed function calls to OpenAI's tool_calls structure.

    Handles both non-streaming and streaming response formats.
    """

    def __init__(self, id_manager: Optional[CallIdManager] = None) -> None:
        """Initialize the response formatter.

        Args:
            id_manager: Optional CallIdManager for ID generation.
                        If None, a new one will be created.
        """
        self._id_manager = id_manager or CallIdManager()

    @property
    def id_manager(self) -> CallIdManager:
        """Get the call ID manager."""
        return self._id_manager

    def format_non_streaming_response(
        self,
        parsed_calls: List[ParsedFunctionCall],
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format a non-streaming response with tool calls.

        Ensures structure: {"role": "assistant", "content": null, "tool_calls": [...]}
        """
        tool_calls = self.format_tool_calls(parsed_calls)
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        }

    def format_tool_call(
        self,
        parsed_call: ParsedFunctionCall,
        call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format a single parsed function call to OpenAI tool_call format.

        Args:
            parsed_call: The parsed function call from Gemini.
            call_id: Optional pre-generated call ID. If None, one will be generated.

        Returns:
            OpenAI tool_call dict:
            {
                "id": "call_abc123...",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": "{\"location\": \"Boston\"}"  # STRING
                }
            }
        """
        if call_id is None:
            call_id = self._id_manager.generate_id()

        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Formatting tool call: {call_id} ({parsed_call.name})")

        # Register the call for tracking

        self._id_manager.register_call(
            call_id=call_id,
            function_name=parsed_call.name,
            arguments=parsed_call.arguments,
        )

        # Arguments must be a JSON string per OpenAI spec
        arguments_str = json.dumps(parsed_call.arguments, ensure_ascii=False)

        tool_call = OpenAIToolCall(
            id=call_id,
            type="function",
            function=OpenAIFunctionCall(
                name=parsed_call.name,
                arguments=arguments_str,
            ),
        )

        return tool_call.model_dump()

    def format_tool_calls(
        self,
        parsed_calls: List[ParsedFunctionCall],
    ) -> List[Dict[str, Any]]:
        """Format multiple parsed function calls to OpenAI tool_calls array.

        Args:
            parsed_calls: List of parsed function calls.

        Returns:
            List of OpenAI tool_call dicts.
        """
        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Formatting {len(parsed_calls)} tool call(s)")
            fc_logger.debug(
                FCModule.RESPONSE,
                f"Formatting {len(parsed_calls)} tool call(s) for OpenAI response",
            )
        return [self.format_tool_call(call) for call in parsed_calls]

    def format_tool_call_delta(
        self,
        index: int,
        call_id: Optional[str] = None,
        function_name: Optional[str] = None,
        arguments_fragment: str = "",
    ) -> Dict[str, Any]:
        """Format a streaming delta chunk for tool calls.

        For the first chunk of a tool call, provide call_id and function_name.
        For subsequent chunks, provide only arguments_fragment.

        Args:
            index: The index of this tool call in the array.
            call_id: The call ID (only on first chunk).
            function_name: The function name (only on first chunk).
            arguments_fragment: Fragment of the arguments JSON string.

        Returns:
            OpenAI streaming delta dict:
            {
                "index": 0,
                "id": "call_abc123",  # Only first chunk
                "type": "function",   # Only first chunk
                "function": {
                    "name": "get_weather",  # Only first chunk
                    "arguments": "{\"loc"   # Streamed fragment
                }
            }
        """
        delta: Dict[str, Any] = {"index": index}

        # First chunk includes id and type
        if call_id is not None:
            delta["id"] = call_id
            delta["type"] = "function"

        # Build function object
        function_delta: Dict[str, Any] = {}
        if function_name is not None:
            function_delta["name"] = function_name
        if arguments_fragment:
            function_delta["arguments"] = arguments_fragment

        if function_delta:
            delta["function"] = function_delta

        return delta

    def format_streaming_first_chunk(
        self,
        index: int,
        parsed_call: ParsedFunctionCall,
    ) -> Dict[str, Any]:
        """Format the first streaming chunk for a function call.

        This chunk includes the call ID, type, function name, and empty arguments.

        Args:
            index: The index of this tool call.
            parsed_call: The parsed function call.

        Returns:
            First delta chunk dict.
        """
        call_id = self._id_manager.generate_id()

        # Register for tracking
        self._id_manager.register_call(
            call_id=call_id,
            function_name=parsed_call.name,
            arguments=parsed_call.arguments,
        )

        return self.format_tool_call_delta(
            index=index,
            call_id=call_id,
            function_name=parsed_call.name,
            arguments_fragment="",
        )

    def format_streaming_chunks(
        self,
        index: int,
        parsed_call: ParsedFunctionCall,
        chunk_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Format all streaming chunks for a complete function call.

        Generates the first chunk with metadata, then chunks of the arguments.

        Args:
            index: The index of this tool call.
            parsed_call: The parsed function call.
            chunk_size: Size of each arguments chunk.

        Returns:
            List of delta chunks for streaming.
        """
        call_id = self._id_manager.generate_id()

        # Register for tracking
        self._id_manager.register_call(
            call_id=call_id,
            function_name=parsed_call.name,
            arguments=parsed_call.arguments,
        )

        chunks: List[Dict[str, Any]] = []

        # First chunk with metadata
        chunks.append(
            self.format_tool_call_delta(
                index=index,
                call_id=call_id,
                function_name=parsed_call.name,
                arguments_fragment="",
            )
        )

        # Arguments chunks
        arguments_str = json.dumps(parsed_call.arguments, ensure_ascii=False)
        for i in range(0, len(arguments_str), chunk_size):
            fragment = arguments_str[i : i + chunk_size]
            chunks.append(
                self.format_tool_call_delta(
                    index=index,
                    call_id=call_id,  # Include ID in all chunks for consistency
                    arguments_fragment=fragment,
                )
            )

        return chunks


# =============================================================================
# Message Builder Helper
# =============================================================================


def build_assistant_message_with_tool_calls(
    tool_calls: List[Dict[str, Any]],
    content: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an OpenAI-compatible assistant message with tool_calls.

    Args:
        tool_calls: List of formatted tool call dicts.
        content: Optional text content (usually None for pure function calls).

    Returns:
        OpenAI message dict:
        {
            "role": "assistant",
            "content": null,  # or text
            "tool_calls": [...]
        }
    """
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }

    if tool_calls:
        message["tool_calls"] = tool_calls

    return message


def get_finish_reason(has_tool_calls: bool) -> str:
    """Determine the appropriate finish_reason.

    Args:
        has_tool_calls: Whether the response contains tool calls.

    Returns:
        "tool_calls" if function calls present, "stop" otherwise.
    """
    return "tool_calls" if has_tool_calls else "stop"


# =============================================================================
# Convenience Functions
# =============================================================================


def convert_openai_tools_to_gemini(
    openai_tools: List[Dict[str, Any]],
) -> str:
    """Convenience function to convert OpenAI tools to Gemini JSON string.

    Args:
        openai_tools: List of OpenAI tool definitions.

    Returns:
        JSON string of Gemini FunctionDeclarations for UI paste.

    Raises:
        SchemaConversionError: If conversion fails.
    """
    converter = SchemaConverter()
    declarations = converter.convert_tools(openai_tools)
    return converter.to_json_string(declarations)


def create_tool_calls_response(
    parsed_calls: List[ParsedFunctionCall],
    content: Optional[str] = None,
) -> tuple[Dict[str, Any], str]:
    """Create a complete tool_calls response tuple.

    Args:
        parsed_calls: List of parsed function calls.
        content: Optional text content.

    Returns:
        Tuple of (message_dict, finish_reason).
    """
    formatter = ResponseFormatter()
    tool_calls = formatter.format_tool_calls(parsed_calls)
    message = build_assistant_message_with_tool_calls(tool_calls, content)
    finish_reason = get_finish_reason(bool(tool_calls))
    return message, finish_reason


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Configuration
    "FunctionCallingMode",
    "FunctionCallingConfig",
    # Schema Conversion
    "SchemaConverter",
    "SchemaConversionError",
    # Call ID Management
    "CallIdManager",
    "PendingCall",
    # Response Parsing Types
    "ParsedFunctionCall",
    # Response Formatting
    "ResponseFormatter",
    "OpenAIFunctionCall",
    "OpenAIToolCall",
    "OpenAIToolCallDelta",
    # Helpers
    "build_assistant_message_with_tool_calls",
    "get_finish_reason",
    # Convenience Functions
    "convert_openai_tools_to_gemini",
    "create_tool_calls_response",
    # FC-001: thoughtSignature Support
    "DUMMY_THOUGHT_SIGNATURE",
    "ensure_thought_signature",
    # FC-002: MCP Response Handling
    "normalize_tool_response",
    "MCPResponseItem",
    # FC-003: Tool Choice Conversion
    "GeminiToolConfig",
    "convert_tool_choice",
    # FC-004: Type Case Normalization
    "TYPE_MAP_UPPER",
    "TYPE_MAP_LOWER",
]
