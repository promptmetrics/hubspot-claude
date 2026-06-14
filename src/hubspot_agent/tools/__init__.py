from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    is_async: bool


registry: dict[str, ToolDef] = {}


def tool(name: str, description: str) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        registry[name] = ToolDef(
            name=name,
            description=description,
            func=func,
            is_async=inspect.iscoroutinefunction(func),
        )
        return func
    return decorator


def get_tool(name: str) -> ToolDef | None:
    return registry.get(name)


def list_tools() -> list[ToolDef]:
    return list(registry.values())


async def invoke_tool(tool_name: str, portal_id: str, **kwargs: Any) -> Any:
    tool_def = get_tool(tool_name)
    if tool_def is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    kwargs["portal_id"] = portal_id
    if tool_def.is_async:
        result = await tool_def.func(**kwargs)
    else:
        result = tool_def.func(**kwargs)

    return result
