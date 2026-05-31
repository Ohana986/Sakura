from __future__ import annotations

import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.chat_reply import ChatReply, parse_chat_reply
from app.debug_log import debug_log, summarize_messages
from app.env_config import load_env_file, save_env_values
from app.prompt_templates import build_segmented_reply_instruction


MAX_API_RETRY_ATTEMPTS = 3
API_RETRY_DELAY_SECONDS = 0.8
ChatMessage = dict[str, Any]
SUPPORTED_CHAT_COMPLETION_PARAMS = {
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "presence_penalty",
    "frequency_penalty",
    "response_format",
    "stream",
    "tools",
    "tool_choice",
}

class ApiConfigError(RuntimeError):
    """API 配置缺失或格式错误。"""


class ApiRequestError(RuntimeError):
    """API 请求失败。"""


@dataclass(frozen=True)
class ApiSettings:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 60

    @classmethod
    def load(cls, env_path: Path) -> "ApiSettings":
        values = load_env_file(env_path)

        base_url = (
            os.getenv("BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or values.get("BASE_URL")
            or values.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        api_key = (
            os.getenv("API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or values.get("API_KEY")
            or values.get("OPENAI_API_KEY")
            or ""
        )
        model = (
            os.getenv("MODEL")
            or os.getenv("OPENAI_MODEL")
            or values.get("MODEL")
            or values.get("OPENAI_MODEL")
            or "gpt-4.1-mini"
        )
        timeout_text = (
            os.getenv("API_TIMEOUT_SECONDS")
            or values.get("API_TIMEOUT_SECONDS")
            or "60"
        )

        try:
            timeout_seconds = int(timeout_text)
        except ValueError:
            timeout_seconds = 60

        return cls(
            base_url=base_url.strip().rstrip("/"),
            api_key=api_key.strip(),
            model=model.strip(),
            timeout_seconds=timeout_seconds,
        )

    def save(self, env_path: Path) -> None:
        """将聊天 API 配置写入 .env，并保留其他配置项。"""
        save_env_values(
            env_path,
            {
                "BASE_URL": self.base_url.strip().rstrip("/"),
                "API_KEY": self.api_key.strip(),
                "MODEL": self.model.strip(),
                "API_TIMEOUT_SECONDS": str(self.timeout_seconds),
            },
        )


class OpenAICompatibleClient:
    def __init__(self, settings: ApiSettings) -> None:
        self.settings = settings

    def update_settings(self, settings: ApiSettings) -> None:
        """运行时更新 API 配置，供设置界面保存后立即生效。"""
        self.settings = settings

    def test_connection(self) -> str:
        """发送一次最小聊天请求，验证 Base URL、API Key 和模型是否可用。"""
        self._ensure_chat_config("缺少 API_KEY。请在设置中填写 API Key。")

        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with only OK.",
                },
            ],
            "temperature": 0,
            "max_tokens": 8,
        }
        data = self._post_chat_completions(payload)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ApiRequestError(f"API 返回格式无法解析：{json.dumps(data, ensure_ascii=False)}") from exc

        return str(content).strip() or "OK"

    def chat(
        self,
        system_prompt: str,
        messages: list[ChatMessage],
        reply_tones: list[str] | None = None,
        reply_portraits: list[str] | None = None,
    ) -> ChatReply:
        segmented_reply_instruction = _build_segmented_reply_instruction(reply_tones, reply_portraits)
        content = self.complete_raw(
            f"{system_prompt.strip()}\n\n{segmented_reply_instruction}",
            messages,
            temperature=0.8,
        )

        reply = parse_chat_reply(content)
        debug_log(
            "API",
            "聊天回复解析完成",
            {
                "segments": len(reply.segments),
                "tone": reply.tone,
                "portraits": [segment.portrait for segment in reply.segments],
                "reply": reply.text,
            },
        )
        return reply

    def complete_raw(
        self,
        system_prompt: str,
        messages: list[ChatMessage],
        temperature: float = 0.8,
        **chat_params: Any,
    ) -> str:
        """返回模型原始文本，供 Agent Runtime 解析工具调用 JSON。"""
        self._ensure_chat_config("缺少 API_KEY。请在 .env 中配置 API_KEY、BASE_URL、MODEL。")

        payload = _build_chat_completion_payload(
            model=self.settings.model,
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
            chat_params=chat_params,
        )
        debug_log(
            "API",
            "准备发送聊天补全请求",
            {
                "base_url": self.settings.base_url,
                "model": self.settings.model,
                "timeout_seconds": self.settings.timeout_seconds,
                "temperature": temperature,
                "message_count": len(payload["messages"]),
                "has_image": messages_contain_image(payload["messages"]),
                "messages": summarize_messages(payload["messages"]),
                "chat_params": _filter_supported_chat_params(chat_params),
            },
        )
        data = self._post_chat_completions(payload)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ApiRequestError(f"API 返回格式无法解析：{json.dumps(data, ensure_ascii=False)}") from exc

        result = str(content).strip()
        debug_log("API", "模型原始文本返回", {"content": result})
        return result

    def _ensure_chat_config(self, api_key_message: str) -> None:
        if not self.settings.api_key:
            raise ApiConfigError(api_key_message)
        if not self.settings.base_url:
            raise ApiConfigError("缺少 BASE_URL。")
        if not self.settings.model:
            raise ApiConfigError("缺少 MODEL。")

    def _post_chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用 OpenAI 兼容的 chat/completions 接口并返回 JSON 数据。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.base_url}/chat/completions"
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
        )

        debug_log(
            "API",
            "HTTP 请求体已构建",
            {
                "url": url,
                "bytes": len(body),
                "payload": payload,
            },
        )
        response_body = self._send_with_retries(request)

        try:
            data: dict[str, Any] = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise ApiRequestError(f"API 返回格式无法解析：{response_body}") from exc

        return data

    def _send_with_retries(self, request: urllib.request.Request) -> str:
        last_error: BaseException | None = None
        for attempt in range(1, MAX_API_RETRY_ATTEMPTS + 1):
            started_at = time.perf_counter()
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.settings.timeout_seconds,
                ) as response:
                    response_body = response.read().decode("utf-8")
                    debug_log(
                        "API",
                        "HTTP 请求成功",
                        {
                            "attempt": attempt,
                            "status": getattr(response, "status", None),
                            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                            "response_body": response_body,
                        },
                    )
                    return response_body
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                debug_log(
                    "API",
                    "HTTP 请求失败",
                    {
                        "attempt": attempt,
                        "status": exc.code,
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                        "error_body": error_body,
                    },
                )
                if exc.code not in {429, 500, 502, 503, 504} or attempt == MAX_API_RETRY_ATTEMPTS:
                    raise ApiRequestError(f"API HTTP {exc.code}: {error_body}") from exc
                last_error = exc
            except urllib.error.URLError as exc:
                debug_log(
                    "API",
                    "URL 请求失败",
                    {
                        "attempt": attempt,
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                        "reason": str(exc.reason),
                    },
                )
                if attempt == MAX_API_RETRY_ATTEMPTS:
                    raise ApiRequestError(f"API 请求失败：{exc.reason}") from exc
                last_error = exc
            except TimeoutError as exc:
                debug_log(
                    "API",
                    "请求超时",
                    {
                        "attempt": attempt,
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                    },
                )
                if attempt == MAX_API_RETRY_ATTEMPTS:
                    raise ApiRequestError("API 请求超时。") from exc
                last_error = exc
            except (ssl.SSLError, ConnectionError, http.client.RemoteDisconnected) as exc:
                debug_log(
                    "API",
                    "连接中断",
                    {
                        "attempt": attempt,
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                        "error": str(exc),
                    },
                )
                if attempt == MAX_API_RETRY_ATTEMPTS:
                    raise ApiRequestError(f"API 连接中断：{exc}") from exc
                last_error = exc

            print(f"[API] 请求失败，准备重试 {attempt}/{MAX_API_RETRY_ATTEMPTS}：{last_error}")
            debug_log(
                "API",
                "准备重试请求",
                {
                    "attempt": attempt,
                    "max_attempts": MAX_API_RETRY_ATTEMPTS,
                    "delay_seconds": API_RETRY_DELAY_SECONDS * attempt,
                    "last_error": str(last_error),
                },
            )
            time.sleep(API_RETRY_DELAY_SECONDS * attempt)

        raise ApiRequestError("API 请求失败。")


def _build_segmented_reply_instruction(
    reply_tones: list[str] | None,
    reply_portraits: list[str] | None = None,
) -> str:
    return build_segmented_reply_instruction(reply_tones, reply_portraits)


def _build_chat_completion_payload(
    *,
    model: str,
    system_prompt: str,
    messages: list[ChatMessage],
    temperature: float,
    chat_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 OpenAI 兼容请求体，并丢弃已知非标准参数。"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt.strip(),
            },
            *messages,
        ],
        "temperature": temperature,
    }
    payload.update(_filter_supported_chat_params(chat_params or {}))
    return payload


def _filter_supported_chat_params(params: dict[str, Any]) -> dict[str, Any]:
    """过滤兼容端点常见不支持的内部参数，避免请求在网关层失败。"""
    filtered: dict[str, Any] = {}
    for key, value in params.items():
        if key not in SUPPORTED_CHAT_COMPLETION_PARAMS or value is None:
            continue
        if key == "max_tokens" and params.get("max_completion_tokens") is not None:
            continue
        filtered[key] = value
    return filtered


def messages_contain_image(messages: list[ChatMessage]) -> bool:
    """检查消息中是否包含 OpenAI 兼容 image_url 内容块。"""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False


def is_vision_unsupported_error(error: BaseException | str) -> bool:
    """识别常见的非视觉模型或兼容接口图片输入错误。"""
    text = str(error).lower()
    markers = (
        "image_url",
        "image input",
        "image inputs",
        "vision",
        "multimodal",
        "modalities",
        "unsupported content",
        "content type",
        "does not support image",
        "only text",
    )
    return any(marker in text for marker in markers)
