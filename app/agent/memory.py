from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


MEMORY_CATEGORIES = {"preference", "project", "habit", "fact"}


@dataclass
class MemoryStore:
    """按 JSON 保存长期记忆和待确认候选记忆。"""

    path: Path | None = None
    values: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return self._load()

    def summary(self, limit: int = 8) -> str:
        data = self._load()
        memories = data["memories"][-limit:]
        pending_updates = data["pending_updates"][-limit:]
        if not memories and not pending_updates:
            return "暂无长期记忆。"

        lines: list[str] = []
        if memories:
            lines.append("已确认记忆：")
            for memory in memories:
                lines.append(
                    f"- [{memory.get('id')}] {memory.get('category')}: {memory.get('content')}"
                )
        if pending_updates:
            lines.append("待确认候选记忆：")
            for update in pending_updates:
                lines.append(
                    f"- [{update.get('id')}] {update.get('category')}: {update.get('content')}"
                )
        return "\n".join(lines)

    def search_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        keyword = _optional_text(arguments, "keyword").lower()
        category = _optional_text(arguments, "category")
        data = self._load()
        memories = [
            memory
            for memory in data["memories"]
            if _matches_memory(memory, keyword, category)
        ]
        return {"memories": memories}

    def propose_memory_update(self, arguments: dict[str, Any]) -> dict[str, Any]:
        category = _normalize_category(_required_text(arguments, "category"))
        content = _required_text(arguments, "content")
        reason = _optional_text(arguments, "reason")
        now = _now_iso()
        update = {
            "id": uuid.uuid4().hex[:8],
            "category": category,
            "content": content,
            "reason": reason,
            "created_at": now,
            "updated_at": now,
        }
        data = self._load()
        data["pending_updates"].append(update)
        self._save(data)
        return {"pending_update": update}

    def confirm_memory_update(self, arguments: dict[str, Any]) -> dict[str, Any]:
        update_id = _required_text(arguments, "id")
        data = self._load()
        for index, update in enumerate(data["pending_updates"]):
            if update.get("id") != update_id:
                continue
            now = _now_iso()
            memory = {
                "id": update["id"],
                "category": update["category"],
                "content": update["content"],
                "created_at": update.get("created_at") or now,
                "updated_at": now,
            }
            data["pending_updates"].pop(index)
            data["memories"].append(memory)
            self._save(data)
            return {"memory": memory}
        raise ValueError(f"未找到候选记忆：{update_id}")

    def forget_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        memory_id = _required_text(arguments, "id")
        data = self._load()
        for index, memory in enumerate(data["memories"]):
            if memory.get("id") != memory_id:
                continue
            removed = data["memories"].pop(index)
            self._save(data)
            return {"forgotten": removed}
        raise ValueError(f"未找到记忆：{memory_id}")

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if self.path is None:
            return _normalize_data(self.values)
        if not self.path.exists():
            return {"memories": [], "pending_updates": []}

        try:
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"记忆文件不是有效 JSON：{self.path}") from exc
        return _normalize_data(raw_data)

    def _save(self, data: dict[str, list[dict[str, Any]]]) -> None:
        normalized = _normalize_data(data)
        if self.path is None:
            self.values = normalized
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _normalize_data(raw_data: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw_data, dict):
        raise ValueError("记忆文件格式无效，顶层必须是 JSON object。")
    memories = _normalize_records(raw_data.get("memories", []), include_reason=False)
    pending_updates = _normalize_records(raw_data.get("pending_updates", []), include_reason=True)
    return {"memories": memories, "pending_updates": pending_updates}


def _normalize_records(records: Any, include_reason: bool) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("记忆文件格式无效，memories 和 pending_updates 必须是列表。")

    result: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        memory_id = item.get("id")
        category = item.get("category")
        content = item.get("content")
        if not all(isinstance(value, str) and value.strip() for value in (memory_id, category, content)):
            continue
        record = {
            "id": memory_id.strip(),
            "category": _normalize_category(category),
            "content": content.strip(),
            "created_at": _text_or_now(item.get("created_at")),
            "updated_at": _text_or_now(item.get("updated_at")),
        }
        if include_reason:
            reason = item.get("reason", "")
            record["reason"] = reason.strip() if isinstance(reason, str) else ""
        result.append(record)
    return result


def _matches_memory(memory: dict[str, Any], keyword: str, category: str) -> bool:
    if category and memory.get("category") != category:
        return False
    if not keyword:
        return True
    content = str(memory.get("content", "")).lower()
    memory_id = str(memory.get("id", "")).lower()
    return keyword in content or keyword in memory_id


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少必填参数：{key}")
    return value.strip()


def _optional_text(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _normalize_category(category: str) -> str:
    category = category.strip()
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"记忆分类必须是：{', '.join(sorted(MEMORY_CATEGORIES))}")
    return category


def _text_or_now(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _now_iso()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
