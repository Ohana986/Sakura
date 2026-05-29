from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import uuid

import pytest

from app.agent.actions import PendingToolAction
from app.agent.memory import MemoryStore
from app.agent.reminders import ReminderStore
from app.agent.runtime import AgentRuntime, SCREEN_OBSERVATION_REQUEST_ACTION
from app.agent.tool_registry import Tool, ToolRegistry
from app.api_client import ApiRequestError, is_vision_unsupported_error, messages_contain_image
from app.screen_observation import (
    SCREEN_OBSERVATION_HISTORY_MARKER,
    ScreenObservation,
    append_observation_marker,
    build_screen_observation_user_message,
    should_observe_screen,
)


def test_add_reminder_delay_seconds_generates_future_time() -> None:
    store = ReminderStore(_runtime_json_path("reminders"))
    before = datetime.now().astimezone()

    result = store.add_reminder({"text": "喝水", "delay_seconds": 30})

    trigger_at = datetime.fromisoformat(result["reminder"]["trigger_at"])
    after = datetime.now().astimezone()
    assert before + timedelta(seconds=25) <= trigger_at <= after + timedelta(seconds=35)


def test_add_reminder_delay_minutes_generates_future_time() -> None:
    store = ReminderStore(_runtime_json_path("reminders"))
    before = datetime.now().astimezone()

    result = store.add_reminder({"text": "休息", "delay_minutes": 2})

    trigger_at = datetime.fromisoformat(result["reminder"]["trigger_at"])
    after = datetime.now().astimezone()
    assert before + timedelta(seconds=115) <= trigger_at <= after + timedelta(seconds=125)


def test_add_reminder_rejects_past_trigger_at() -> None:
    store = ReminderStore(_runtime_json_path("reminders"))
    past = (datetime.now().astimezone() - timedelta(minutes=1)).isoformat(timespec="seconds")

    with pytest.raises(ValueError, match="提醒时间必须晚于当前时间"):
        store.add_reminder({"text": "过期提醒", "trigger_at": past})


def test_due_reminders_and_mark_completed() -> None:
    store = ReminderStore(_runtime_json_path("reminders"))
    now = datetime.now().astimezone()
    due = store.add_reminder({"text": "到点", "delay_seconds": 1})["reminder"]
    future = store.add_reminder({"text": "稍后", "delay_minutes": 5})["reminder"]

    due["trigger_at"] = (now - timedelta(seconds=1)).isoformat(timespec="seconds")
    future["trigger_at"] = (now + timedelta(minutes=5)).isoformat(timespec="seconds")
    store._save({"reminders": [due, future]})

    due_reminders = store.due_reminders(now)
    assert [reminder["id"] for reminder in due_reminders] == [due["id"]]

    store.mark_completed(due["id"])

    assert store.due_reminders(now) == []


def test_memory_propose_update_only_creates_pending_record() -> None:
    store = MemoryStore(_runtime_json_path("memory"))

    result = store.propose_memory_update(
        {
            "category": "preference",
            "content": "主人喜欢中文回复",
            "reason": "长期偏好",
        }
    )

    snapshot = store.snapshot()
    assert snapshot["memories"] == []
    assert snapshot["pending_updates"] == [result["pending_update"]]


def test_memory_confirm_update_moves_pending_to_memories() -> None:
    store = MemoryStore(_runtime_json_path("memory"))
    pending = store.propose_memory_update(
        {
            "category": "project",
            "content": "Sakura 正在稳定 Agent 内核",
        }
    )["pending_update"]

    result = store.confirm_memory_update({"id": pending["id"]})

    snapshot = store.snapshot()
    assert snapshot["pending_updates"] == []
    assert snapshot["memories"] == [result["memory"]]


def test_tool_registry_requires_confirmation_returns_pending_action() -> None:
    registry = ToolRegistry(
        [
            Tool(
                name="open_url",
                description="打开网页",
                handler=lambda _arguments: {"opened": True},
                requires_confirmation=True,
            )
        ]
    )

    result = registry.prepare_or_execute(
        "open_url",
        {"url": "https://example.com"},
        "用户要求打开网页",
    )

    assert isinstance(result, PendingToolAction)
    assert result.tool_name == "open_url"
    assert result.arguments == {"url": "https://example.com"}


def test_tool_registry_free_access_executes_normal_confirmation_tool() -> None:
    registry = ToolRegistry(
        [
            Tool(
                name="open_url",
                description="打开网页",
                handler=lambda _arguments: {"opened": True},
                requires_confirmation=True,
            )
        ]
    )
    registry.set_free_access_enabled(True)

    result = registry.prepare_or_execute("open_url", {"url": "https://example.com"})

    assert not isinstance(result, PendingToolAction)
    assert result.success
    assert result.content == {"opened": True}


def test_tool_registry_free_access_keeps_file_delete_confirmation() -> None:
    registry = ToolRegistry(
        [
            Tool(
                name="delete_file",
                description="删除本地文件",
                handler=lambda _arguments: {"deleted": True},
                requires_confirmation=True,
                confirmation_risk="delete_file",
            )
        ]
    )
    registry.set_free_access_enabled(True)

    result = registry.prepare_or_execute("delete_file", {"path": "a.txt"})

    assert isinstance(result, PendingToolAction)
    assert result.tool_name == "delete_file"


def test_model_vision_enabled_allows_model_to_request_screen_observation() -> None:
    class ScreenRequestClient:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete_raw(self, system_prompt, *_args, **_kwargs) -> str:  # type: ignore[no-untyped-def]
            self.prompts.append(system_prompt)
            return (
                '{"reply":{"segments":[{"ja":"見るね。","zh":"我看看。","tone":"提醒"}]},'
                '"tool_calls":[{"name":"observe_screen","arguments":{},"reason":"需要当前画面"}]}'
            )

    client = ScreenRequestClient()
    runtime = AgentRuntime(
        api_client=client,  # type: ignore[arg-type]
        system_prompt="你是 Sakura。",
        tools=ToolRegistry(),
    )
    runtime.set_model_vision_enabled(True)

    result = runtime.handle_user_message([{"role": "user", "content": "这个界面哪里不对"}])

    assert "observe_screen" in client.prompts[0]
    assert result.actions
    assert result.actions[0].type == SCREEN_OBSERVATION_REQUEST_ACTION


def test_screen_observation_message_uses_openai_image_url_format() -> None:
    observation = ScreenObservation(
        data_url="data:image/jpeg;base64,abc123",
        width=1280,
        height=720,
        captured_at="2026-05-29T20:00:00+08:00",
        screen_name="DISPLAY1",
    )

    message = build_screen_observation_user_message("帮我看这个", observation)

    assert message["role"] == "user"
    content = message["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1] == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/jpeg;base64,abc123",
            "detail": "low",
        },
    }
    assert messages_contain_image([message])


def test_screen_observation_history_marker_does_not_store_image_data() -> None:
    observation = ScreenObservation(
        data_url="data:image/jpeg;base64,secret",
        width=800,
        height=600,
        captured_at="2026-05-29T20:00:00+08:00",
        screen_name="DISPLAY1",
    )

    history_text = append_observation_marker("看看屏幕", observation)

    assert SCREEN_OBSERVATION_HISTORY_MARKER in history_text
    assert "data:image/jpeg;base64" not in history_text
    assert "secret" not in history_text


def test_screen_observation_trigger_requires_explicit_text() -> None:
    assert should_observe_screen("帮我看这个界面哪里不对")
    assert should_observe_screen("看看当前画面")
    assert not should_observe_screen("今天聊点什么")


def test_vision_unsupported_error_gets_local_fallback_reply() -> None:
    class VisionUnsupportedClient:
        def complete_raw(self, *_args, **_kwargs) -> str:  # type: ignore[no-untyped-def]
            raise ApiRequestError("model does not support image_url content")

    observation = ScreenObservation(
        data_url="data:image/jpeg;base64,abc123",
        width=1280,
        height=720,
        captured_at="2026-05-29T20:00:00+08:00",
        screen_name="DISPLAY1",
    )
    runtime = AgentRuntime(
        api_client=VisionUnsupportedClient(),  # type: ignore[arg-type]
        system_prompt="你是 Sakura。",
        tools=ToolRegistry(),
    )

    result = runtime.handle_user_message([build_screen_observation_user_message("看看屏幕", observation)])

    assert "不支持图片输入" in result.reply.translation
    assert not result.actions


def test_plain_text_messages_do_not_contain_image() -> None:
    assert not messages_contain_image([{"role": "user", "content": "普通聊天"}])
    assert is_vision_unsupported_error("This model does not support image input")


def _runtime_json_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "__pycache__" / "test_runtime" / uuid.uuid4().hex
    return root / f"{name}.json"
