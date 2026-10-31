"""Bounded Nebius chat session for tool-calling specialist agents."""

import json
import ssl
from collections.abc import Callable
from typing import Any

import httpx
import truststore
from pydantic import BaseModel, ValidationError

from ..config import settings
from .nebius import ProviderError


class AgentClient:
    def __init__(self, role: str, prompt_version: str, max_calls: int = 6):
        self.role, self.prompt_version, self.max_calls = role, prompt_version, max_calls
        self.config = settings()
        if not self.config.key or not self.config.model:
            raise ProviderError("Configure Nebius key and model before running specialist agents.")
        if self.config.base_url.rstrip("/") != "https://api.tokenfactory.nebius.com/v1":
            raise ProviderError("Specialist agents require the verified Nebius endpoint.")
        self.calls = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.response_model = ""
        self.client = httpx.Client(
            timeout=httpx.Timeout(60, connect=10),
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def chat(self, messages: list[dict], **options: Any) -> dict:
        for attempt in range(2):
            if self.calls >= self.max_calls:
                raise ProviderError(f"{self.role}: model-call budget exhausted; review stopped.")
            self.calls += 1
            try:
                response = self.client.post(
                    self.config.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.config.key},
                    json={
                        "model": self.config.model,
                        "temperature": 0,
                        "max_tokens": 2500,
                        "chat_template_kwargs": {"enable_thinking": False},
                        "messages": messages,
                        **options,
                    },
                )
            except httpx.TransportError:
                if not attempt:
                    continue
                raise ProviderError(f"{self.role}: connection failed after retry.") from None
            if response.status_code in {429, 500, 502, 503, 504} and not attempt:
                continue
            if response.status_code != 200:
                raise ProviderError(
                    f"{self.role}: Nebius HTTP {response.status_code}; review stopped."
                )
            try:
                body = response.json()
                for key in self.usage:
                    self.usage[key] += int(body.get("usage", {}).get(key) or 0)
                choice = body["choices"][0]
                if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                    raise ValueError("Incomplete response.")
                self.response_model = body.get("model") or self.config.model
                return choice["message"]
            except (ValueError, TypeError, KeyError, IndexError):
                raise ProviderError(
                    f"{self.role}: invalid or incomplete provider response."
                ) from None
        raise ProviderError(f"{self.role}: request did not complete.")

    def structured(self, messages: list[dict], model: type[BaseModel], validate: Callable) -> Any:
        schema = {
            "type": "json_schema",
            "json_schema": {"name": self.role, "strict": True, "schema": model.model_json_schema()},
        }
        for attempt in range(2):
            message = self.chat(messages, response_format=schema)
            try:
                return validate(model.model_validate_json(message.get("content") or ""))
            except (ValueError, TypeError, ValidationError) as exc:
                if attempt:
                    raise ProviderError(
                        f"{self.role}: structured output failed verification after repair."
                    ) from None
                feedback = "Invalid schema." if isinstance(exc, ValidationError) else str(exc)[:500]
                messages = messages + [
                    {
                        "role": "user",
                        "content": "Verification failed: "
                        + feedback
                        + " Return a corrected JSON object using only the checked tool results.",
                    }
                ]

        raise ProviderError(f"{self.role}: verification failed.")

    def metadata(self) -> dict:
        return {
            "model_calls": self.calls,
            "usage": dict(self.usage),
            "model": self.config.model,
            "response_model": self.response_model,
            "prompt_version": self.prompt_version,
        }


def call_tool_round(
    client: AgentClient, messages: list[dict], tools: dict[str, Callable], trace: list[dict]
) -> set[str]:
    # The provider's native required-tool mode emitted repeated calls in live
    # testing. A strict action schema permits exactly one selected tool per turn.
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": client.role + "_tool_action",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "arguments"],
                "properties": {
                    "tool": {"type": "string", "enum": list(tools)},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {},
                        "required": [],
                    },
                },
            },
        },
    }
    selection = messages + [
        {
            "role": "user",
            "content": json.dumps(
                {
                    "instruction": "Select exactly one available tool to execute now. Return JSON tool and arguments.",
                    "available_tools": {name: fn.__doc__ or name for name, fn in tools.items()},
                }
            ),
        }
    ]
    message = client.chat(selection, response_format=schema)
    try:
        action = json.loads(message.get("content") or "")
        if (
            set(action) != {"tool", "arguments"}
            or action["tool"] not in tools
            or action["arguments"] != {}
        ):
            raise ValueError("Invalid tool action.")
        name = action["tool"]
        output = tools[name]()
        trace.append(
            {"name": name, "arguments": {}, "invocation": "validated_json_action", "result": output}
        )
        messages.append({"role": "assistant", "content": json.dumps(action)})
        messages.append(
            {
                "role": "user",
                "content": json.dumps({"tool_result": {"name": name, "result": output}}),
            }
        )
        return {name}
    except (KeyError, TypeError, ValueError):
        raise ProviderError(
            f"{client.role}: invalid tool request; no packet was accepted."
        ) from None
