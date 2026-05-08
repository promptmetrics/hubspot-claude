from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


_READ_PREFIXES = ("hubspot_get_", "hubspot_search_", "hubspot_list_")


class QueryCache:
    TTL_SECONDS = 300  # 5 minutes

    def __init__(self, portal_id: str) -> None:
        self.portal_id = portal_id
        self.base_dir = Path.home() / ".claude" / "hubspot" / portal_id
        self.cache_file = self.base_dir / "query_cache.json"
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                self._data = json.loads(self.cache_file.read_text())
            except (json.JSONDecodeError, TypeError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self._data, indent=2))

    @staticmethod
    def _make_key(tool_name: str, kwargs: dict[str, Any]) -> str:
        # Exclude non-serializable / non-semantic args
        filtered = {k: v for k, v in kwargs.items() if k not in {"client", "portal_id"}}
        canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{tool_name}:{canonical}".encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _extract_domain(kwargs: dict[str, Any]) -> str | None:
        return kwargs.get("object_type") or kwargs.get("domain")

    def get(self, tool_name: str, kwargs: dict[str, Any]) -> dict[str, Any] | None:
        key = self._make_key(tool_name, kwargs)
        entry = self._data.get(key)
        if entry is None:
            return None
        if time.time() - entry["ts"] > self.TTL_SECONDS:
            del self._data[key]
            self._save()
            return None
        return entry["result"]

    def set(
        self,
        tool_name: str,
        kwargs: dict[str, Any],
        result: dict[str, Any],
        domain: str | None = None,
    ) -> None:
        key = self._make_key(tool_name, kwargs)
        self._data[key] = {
            "result": result,
            "ts": time.time(),
            "tool": tool_name,
            "domain": domain,
        }
        self._save()

    def invalidate_domain(self, domain: str) -> None:
        to_remove = [k for k, v in self._data.items() if v.get("domain") == domain]
        for k in to_remove:
            del self._data[k]
        if to_remove:
            self._save()

    def invalidate_tool(self, tool_name: str) -> None:
        to_remove = [k for k, v in self._data.items() if v.get("tool") == tool_name]
        for k in to_remove:
            del self._data[k]
        if to_remove:
            self._save()

    def clear(self) -> None:
        self._data = {}
        self._save()

    def stats(self) -> dict[str, Any]:
        now = time.time()
        valid = 0
        expired = 0
        by_tool: dict[str, int] = {}
        for entry in self._data.values():
            if now - entry["ts"] <= self.TTL_SECONDS:
                valid += 1
            else:
                expired += 1
            by_tool[entry.get("tool", "unknown")] = by_tool.get(entry.get("tool", "unknown"), 0) + 1
        return {"valid": valid, "expired": expired, "total": len(self._data), "by_tool": by_tool}


def is_read_tool(tool_name: str) -> bool:
    return tool_name.startswith(_READ_PREFIXES)
