"""agent/tool_loop.py - Shared tool-call loop execution

Extracted from loop.py and parallel_core.py to eliminate duplication.
Both files had independent implementations of the same pattern:
  send messages to LLM -> parse tool calls -> execute tools -> append results -> repeat
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Awaitable

logger = logging.getLogger(__name__)


async def run_tool_loop(
    client,
    messages: List[Dict],
    system_prompt: str,
    tools_schema: Optional[List[Dict]],
    execute_tool: Callable[[str, Dict], Awaitable[Any]],
    max_turns: int = 10,
    result_truncate: int = 3000,
    on_tool_call: Optional[Callable] = None,
    on_turn_start: Optional[Callable] = None,
) -> tuple:
    """Execute a tool-call loop: LLM -> tool calls -> execute -> repeat.

    Args:
        client: LLM client with .chat() method
        messages: Conversation messages (mutated in place)
        system_prompt: System prompt string
        tools_schema: Tool definitions for function calling
        execute_tool: Async callable(tool_name, tool_args) -> result
        max_turns: Maximum iteration count
        result_truncate: Truncate tool results beyond this length
        on_tool_call: Optional callback(tool_name, tool_args, turn) before execution
        on_turn_start: Optional callback(turn) at start of each turn

    Returns:
        (final_reply: str, completed: bool, tool_calls_log: list)
    """
    tool_calls_log = []
    final_reply = ""
    completed = False

    for turn in range(max_turns):
        if on_turn_start:
            on_turn_start(turn)

        try:
            response = await client.chat(
                messages=messages,
                system=system_prompt,
                tools=tools_schema if tools_schema is not None else None
            )
        except Exception as e:
            final_reply = f"LLM调用失败: {e}"
            break

        content = response.get("content", "") or ""
        tool_calls = response.get("tool_calls", [])

        # No tool calls -> final reply
        if not tool_calls:
            final_reply = content
            completed = True
            break

        # Record assistant message with tool calls
        assistant_msg = {"role": "assistant", "content": content}
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ]
        messages.append(assistant_msg)

        # Execute each tool call
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc["arguments"]

            if on_tool_call:
                on_tool_call(tool_name, tool_args, turn)

            try:
                result = await execute_tool(tool_name, tool_args)
                result_str = (
                    json.dumps(result, ensure_ascii=False, default=str)
                    if not isinstance(result, str)
                    else result
                )
            except Exception as e:
                result_str = f"[工具错误] {tool_name}: {e}"

            # Truncate long results
            if len(result_str) > result_truncate:
                result_str = result_str[:result_truncate] + "\n... [结果已截断]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

            tool_calls_log.append({
                "turn": turn,
                "tool": tool_name,
                "args": {k: str(v)[:100] for k, v in tool_args.items()},
            })

    if not completed and not final_reply:
        final_reply = "[达到最大工具调用轮数]"

    return final_reply, completed, tool_calls_log
