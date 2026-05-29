from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.actions import PendingToolAction


ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    """内部工具定义。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None
    requires_confirmation: bool = False
    confirmation_risk: str = "normal"


@dataclass(frozen=True)
class ToolExecutionResult:
    """工具执行结果，统一交回模型做最终表述。"""

    tool_name: str
    success: bool
    content: dict[str, Any] | str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tool_name": self.tool_name,
            "success": self.success,
            "content": self.content,
        }
        if self.error:
            data["error"] = self.error
        return data


class ToolRegistry:
    """管理 Agent 可用工具，后续 MCP Provider 会挂到这一层。"""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.free_access_enabled = False
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def describe_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "requires_confirmation": tool.requires_confirmation,
            }
            for tool in self.all()
        ]

    def set_free_access_enabled(self, enabled: bool) -> None:
        """开启后普通确认工具直接执行，文件删除类高风险工具仍保留确认。"""
        self.free_access_enabled = enabled

    def prepare_or_execute(
        self,
        name: str,
        arguments: dict[str, Any],
        reason: str = "",
    ) -> ToolExecutionResult | PendingToolAction:
        tool = self.get(name)
        if tool is None or not tool.requires_confirmation:
            return self.execute(name, arguments)
        if self.free_access_enabled and not _is_file_delete_risk(tool):
            return self.execute(name, arguments)
        if not isinstance(arguments, dict):
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error="工具参数必须是 JSON object。",
            )
        return PendingToolAction.create(
            tool_name=name,
            arguments=arguments,
            reason=reason,
        )

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self.get(name)
        if tool is None:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=f"未知工具：{name}",
            )
        if tool.handler is None:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=f"工具未配置处理器：{name}",
            )
        if not isinstance(arguments, dict):
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error="工具参数必须是 JSON object。",
            )

        try:
            content = tool.handler(arguments)
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=str(exc),
            )
        return ToolExecutionResult(
            tool_name=name,
            success=True,
            content=content if isinstance(content, (dict, str)) else str(content),
        )


def _is_file_delete_risk(tool: Tool) -> bool:
    """识别删除文件相关高风险工具，避免自由访问模式误放行。"""
    if tool.confirmation_risk in {"delete_file", "file_delete", "destructive_file"}:
        return True
    normalized = tool.name.lower()
    return any(
        marker in normalized
        for marker in (
            "delete_file",
            "remove_file",
            "unlink_file",
            "delete_path",
            "remove_path",
            "delete_local_file",
            "remove_local_file",
        )
    )
