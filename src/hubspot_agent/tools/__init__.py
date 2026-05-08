from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from hubspot_agent.query_cache import QueryCache, is_read_tool


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


def _extract_domain(kwargs: dict[str, Any]) -> str | None:
    return kwargs.get("object_type") or kwargs.get("domain")


async def invoke_tool(name: str, portal_id: str, **kwargs: Any) -> Any:
    tool_def = get_tool(name)
    if tool_def is None:
        raise ValueError(f"Unknown tool: {name}")

    cache = QueryCache(portal_id)

    if is_read_tool(name):
        cached = cache.get(name, kwargs)
        if cached is not None:
            return cached

    if tool_def.is_async:
        result = await tool_def.func(**kwargs)
    else:
        result = tool_def.func(**kwargs)

    if is_read_tool(name):
        domain = _extract_domain(kwargs)
        cache.set(name, kwargs, result, domain=domain)
    else:
        domain = _extract_domain(kwargs)
        if domain:
            cache.invalidate_domain(domain)

    return result
