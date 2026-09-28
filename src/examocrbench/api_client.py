from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image


class ApiError(RuntimeError):
    pass


def image_data_uri(path: str | Path, target_long_edge: int = 0) -> str:
    image_path = Path(path)
    with Image.open(image_path) as source:
        source.load()
        image = source.convert("RGB")
        if target_long_edge > 0 and max(image.size) > target_long_edge:
            scale = target_long_edge / max(image.size)
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


class ApiClient:
    """Small protocol adapter for common multimodal API formats."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        protocol: str = "chat",
        timeout: float = 900,
        retries: int = 3,
        target_long_edge: int = 0,
        chat_json_mode: bool = False,
        chat_thinking_disabled: bool = False,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.protocol = protocol
        self.timeout = timeout
        self.retries = max(1, retries)
        self.target_long_edge = target_long_edge
        self.chat_json_mode = chat_json_mode
        self.chat_thinking_disabled = chat_thinking_disabled

    def _request(self, model: str, prompt: str, image_path: Path, max_tokens: int) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        image_uri = image_data_uri(image_path, self.target_long_edge)
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, self.retries + 1):
            started = time.monotonic()
            try:
                payload, headers = self._payload(model, prompt, image_uri, max_tokens)
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
                detail = {
                    "attempt": attempt,
                    "http_status": response.status_code,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
                if response.status_code >= 400:
                    detail["response_excerpt"] = response.text[:2000]
                    attempts.append(detail)
                    raise ApiError(f"HTTP {response.status_code}: {response.text[:500]}")
                body = response.json()
                attempts.append(detail)
                return self._extract(body), body, attempts
            except Exception as exc:  # noqa: BLE001
                if not attempts or attempts[-1].get("attempt") != attempt:
                    attempts.append({"attempt": attempt, "elapsed_seconds": round(time.monotonic() - started, 3)})
                attempts[-1]["error"] = str(exc)
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
        raise ApiError(attempts[-1].get("error", "API request failed"))

    def _payload(self, model: str, prompt: str, image_uri: str, max_tokens: int) -> tuple[dict[str, Any], dict[str, str]]:
        if self.protocol == "responses":
            payload = {
                "model": model,
                "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_uri, "detail": "high"},
                ]}],
                "max_output_tokens": max_tokens,
            }
            return payload, {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.protocol in {"anthropic", "anthropic_bearer"}:
            media_type, encoded = image_uri.split(",", 1)
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type[5:-7], "data": encoded}},
                    {"type": "text", "text": prompt},
                ]}],
            }
            headers = {"anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            if self.protocol == "anthropic_bearer":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                headers["x-api-key"] = self.api_key
            return payload, headers
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_uri}},
            ]}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.chat_json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.chat_thinking_disabled:
            payload["thinking"] = {"type": "disabled"}
        return payload, {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _extract(self, body: dict[str, Any]) -> str:
        if self.protocol == "responses":
            output_text = body.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text.strip()
            parts: list[str] = []

            def visit(value: Any) -> None:
                if isinstance(value, dict):
                    text = value.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                    for child in value.values():
                        visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)

            visit(body.get("output") or [])
            return "\n".join(dict.fromkeys(parts)).strip()
        if self.protocol in {"anthropic", "anthropic_bearer"}:
            content = body.get("content") or []
            return "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict)).strip()
        choices = body.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = (message or {}).get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        return str(content or "").strip()

    def call(self, model: str, prompt: str, image_path: str | Path, max_tokens: int) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        return self._request(model, prompt, Path(image_path), max_tokens)
