import logging
import os
from typing import Any

from anthropic import AsyncAnthropic

from app.agents.context import ToolContext
from app.agents.prompts import SYSTEM_PROMPT
from app.agents.tools import TOOLS, TOOLS_BY_NAME

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
MAX_ITERATIONS = 10
MAX_OUTPUT_TOKENS = 1024


class Copilot:
    def __init__(self, anthropic_api_key: str):
        self._client = AsyncAnthropic(api_key=anthropic_api_key)
        self._tool_schemas = [t.to_anthropic_schema() for t in TOOLS]

    async def chat(self, user_message: str, ctx: ToolContext) -> dict:
        """Run the agent loop for a single user message.

        Returns:
          {
            "reply": "<final assistant text>",
            "tool_calls": [{"name": ..., "input": ..., "output": ...}, ...],
          }
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]
        tool_trace: list[dict] = []

        for iteration in range(MAX_ITERATIONS):
            logger.info("copilot_iteration", extra={"iteration": iteration})

            response = await self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                tools=self._tool_schemas,
                messages=messages,
            )

            # Append the assistant's full response (text + tool_use blocks) as-is.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                reply = _extract_text(response.content)
                return {"reply": reply, "tool_calls": tool_trace}

            if response.stop_reason == "tool_use":
                tool_results = await self._run_tool_calls(response.content, ctx, tool_trace)
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason (max_tokens, pause_turn, etc.)
            logger.warning(
                "copilot_unexpected_stop", extra={"stop_reason": response.stop_reason}
            )
            reply = _extract_text(response.content) or "(no response)"
            return {"reply": reply, "tool_calls": tool_trace}

        return {
            "reply": "I hit my reasoning budget before finishing. Try a more specific request.",
            "tool_calls": tool_trace,
        }

    async def _run_tool_calls(
        self, assistant_content: list, ctx: ToolContext, trace: list[dict]
    ) -> list[dict]:
        """Execute every tool_use block in the assistant's response.
        Returns the list of tool_result blocks to feed back as the next user turn.
        """
        results = []
        for block in assistant_content:
            if block.type != "tool_use":
                continue

            tool = TOOLS_BY_NAME.get(block.name)
            if tool is None:
                output = {"error": f"Unknown tool: {block.name}"}
                is_error = True
            else:
                try:
                    output = await tool.invoke(block.input, ctx)
                    is_error = False
                except Exception as e:
                    logger.exception("tool_invocation_failed", extra={"tool": block.name})
                    output = {"error": f"{type(e).__name__}: {e}"}
                    is_error = True

            trace.append({"name": block.name, "input": block.input, "output": output})

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _stringify(output),
                "is_error": is_error,
            })
        return results


def _extract_text(content: list) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def _stringify(output: Any) -> str:
    import json
    return json.dumps(output, default=str)