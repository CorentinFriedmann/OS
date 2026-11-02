"""Moteur local : Ollama (http://127.0.0.1:11434), 100 % privé et hors ligne."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Iterator

from ..persona import SYSTEM_PROMPT
from . import BackendError, Cancelled, Emit, StepResult, ToolCall

THINKING_FAMILIES = ("qwen3", "deepseek-r1", "magistral")


class OllamaBackend:
    name = "local"

    def __init__(self, config: dict):
        local = config["local"]
        self.url = local["url"].rstrip("/")
        self.model = local["model"]
        self.num_ctx = int(local.get("num_ctx", 8192))
        self.keep_alive = local.get("keep_alive", "30m")
        self._availability: tuple[float, tuple[bool, str]] | None = None

    # --- HTTP -----------------------------------------------------------------
    def _request(self, path: str, payload: dict | None = None, timeout: float = 300):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.url + path, data=data, headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - URL locale configurée

    def _stream_lines(self, path: str, payload: dict) -> Iterator[dict]:
        try:
            response = self._request(path, payload)
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            try:
                message = json.loads(body).get("error", body)
            except json.JSONDecodeError:
                message = body
            raise BackendError(f"L'IA locale a répondu une erreur : {message}") from error
        except (urllib.error.URLError, OSError) as error:
            raise BackendError("L'IA locale (Ollama) ne répond pas. Lance « systemctl start ollama ».") from error
        with response:
            for raw in response:
                line = raw.strip()
                if line:
                    yield json.loads(line)

    # --- disponibilité ------------------------------------------------------------
    def installed_models(self) -> list[str]:
        with self._request("/api/tags", timeout=2) as response:
            return [m.get("name", "") for m in json.load(response).get("models", [])]

    def available(self) -> tuple[bool, str]:
        now = time.monotonic()
        if self._availability and now - self._availability[0] < 15:
            return self._availability[1]
        try:
            names = self.installed_models()
            wanted = {self.model, f"{self.model}:latest"}
            ok = any(name in wanted for name in names)
            result = (True, "") if ok else (False, f"Le modèle local {self.model} n'est pas téléchargé (nova setup).")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            result = (False, "L'IA locale (Ollama) n'est pas démarrée.")
        self._availability = (now, result)
        return result

    # --- un tour de génération -----------------------------------------------------
    def build_payload(self, conversation, tools: list, think_flag: bool = True) -> dict:
        payload = {
            "model": self.model,
            "messages": conversation.to_ollama(SYSTEM_PROMPT),
            "tools": [
                {"type": "function", "function": {
                    "name": tool.name, "description": tool.description, "parameters": tool.parameters,
                }} for tool in tools
            ],
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.4},
        }
        if think_flag and self.model.startswith(THINKING_FAMILIES):
            payload["think"] = False  # réponses immédiates : pas de réflexion longue en local
        return payload

    def step(self, conversation, tools: list, emit: Emit, cancel: threading.Event) -> StepResult:
        payload = self.build_payload(conversation, tools)
        try:
            return self._run(payload, emit, cancel)
        except BackendError as error:
            if "think" in str(error).lower() and "think" in payload:
                payload.pop("think")  # ancienne version d'Ollama : on réessaie sans ce réglage
                return self._run(payload, emit, cancel)
            raise

    def _run(self, payload: dict, emit: Emit, cancel: threading.Event) -> StepResult:
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        stop_reason, usage = "end_turn", {}
        for chunk in self._stream_lines("/api/chat", payload):
            if cancel.is_set():
                raise Cancelled()
            if chunk.get("error"):
                raise BackendError(f"L'IA locale a répondu une erreur : {chunk['error']}")
            message = chunk.get("message") or {}
            delta = message.get("content") or ""
            if delta:
                text_parts.append(delta)
                emit({"type": "text", "text": delta})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):  # certains modèles renvoient une chaîne JSON
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        pass
                calls.append(ToolCall(id=call.get("id") or f"local_{len(calls)}",
                                      name=function.get("name", ""), arguments=arguments))
            if chunk.get("done"):
                stop_reason = {"length": "max_tokens"}.get(chunk.get("done_reason", ""), "end_turn")
                usage = {"input_tokens": chunk.get("prompt_eval_count", 0),
                         "output_tokens": chunk.get("eval_count", 0)}
        if calls and stop_reason == "end_turn":
            stop_reason = "tool_use"
        return StepResult("".join(text_parts), calls, stop_reason, model=self.model, usage=usage)

    # --- téléchargement d'un modèle -----------------------------------------------
    def pull(self, model: str, progress: Callable[[str, float], None]) -> None:
        for chunk in self._stream_lines("/api/pull", {"model": model, "stream": True}):
            if chunk.get("error"):
                raise BackendError(chunk["error"])
            total, done = chunk.get("total") or 0, chunk.get("completed") or 0
            progress(chunk.get("status", ""), (done / total) if total else -1.0)
