"""Historique d'une conversation, indépendant du moteur (local ou cloud).

Règle importante côté Claude : l'historique est en « ajout seul ». Les tours
produits par Claude (avec leurs blocs de réflexion) sont renvoyés tels quels,
jamais modifiés ; on ne fait qu'ajouter de nouveaux messages à la fin.
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    items: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    # --- ajout --------------------------------------------------------------
    def _touch(self) -> None:
        self.updated = time.time()

    def add_user(self, text: str, context: str = "") -> None:
        self.items.append({"kind": "user", "text": text, "context": context, "time": time.time()})
        self._touch()

    def add_assistant(self, backend: str, text: str, tool_calls: list[dict] | None = None,
                      raw: list[dict] | None = None, model: str = "", final: bool = True) -> None:
        self.items.append({
            "kind": "assistant", "backend": backend, "text": text, "tool_calls": tool_calls or [],
            "raw": raw, "model": model, "final": final, "time": time.time(),
        })
        self._touch()

    def add_tool_results(self, backend: str, results: list[dict]) -> None:
        self.items.append({"kind": "tools", "backend": backend, "results": results, "time": time.time()})
        self._touch()

    # --- état ---------------------------------------------------------------
    def exchanges(self) -> int:
        return sum(1 for item in self.items if item["kind"] == "user")

    def idle_minutes(self) -> float:
        return (time.time() - self.updated) / 60

    def last_backend(self) -> str | None:
        for item in reversed(self.items):
            if item["kind"] == "assistant":
                return item["backend"]
        return None

    # --- format Claude (Messages API) ---------------------------------------
    def to_claude(self, supports_system_messages: bool = True) -> list[dict]:
        messages: list[dict] = []
        local_actions: list[str] = []
        for item in self.items:
            kind = item["kind"]
            if kind == "user":
                if item["context"] and supports_system_messages:
                    messages.append({"role": "user", "content": item["text"]})
                    # Message « système » en cours de conversation : canal de l'OS,
                    # sans casser le cache du début de la conversation.
                    messages.append({"role": "system", "content": item["context"]})
                elif item["context"]:
                    messages.append({"role": "user", "content": f"[{item['context']}]\n\n{item['text']}"})
                else:
                    messages.append({"role": "user", "content": item["text"]})
            elif kind == "assistant" and item["backend"] == "cloud":
                messages.append({"role": "assistant", "content": item["raw"] or [{"type": "text", "text": item["text"] or "…"}]})
            elif kind == "tools" and item["backend"] == "cloud":
                messages.append({"role": "user", "content": [_claude_tool_result(r) for r in item["results"]]})
            elif kind == "assistant":  # tour produit par le modèle local
                local_actions += [call["name"] for call in item["tool_calls"]]
                if item["final"]:
                    text = item["text"] or "(action effectuée)"
                    if local_actions:
                        text += f"\n\n(Actions effectuées en local : {', '.join(local_actions)})"
                    messages.append({"role": "assistant", "content": text})
                    local_actions = []
        return messages

    # --- format Ollama (/api/chat) --------------------------------------------
    def to_ollama(self, system_prompt: str, max_messages: int = 24) -> list[dict]:
        body: list[dict] = []
        last_user = max((i for i, it in enumerate(self.items) if it["kind"] == "user"), default=-1)
        for index, item in enumerate(self.items):
            kind = item["kind"]
            if kind == "user":
                if item["context"] and index == last_user:  # seul le contexte actuel est utile
                    body.append({"role": "system", "content": item["context"]})
                body.append({"role": "user", "content": item["text"]})
            elif kind == "assistant" and item["backend"] == "local":
                message: dict[str, Any] = {"role": "assistant", "content": item["text"]}
                if item["tool_calls"]:
                    message["tool_calls"] = [
                        {"function": {"name": c["name"], "arguments": c["arguments"]}} for c in item["tool_calls"]
                    ]
                body.append(message)
            elif kind == "tools" and item["backend"] == "local":
                body += [{"role": "tool", "content": r["content"], "tool_name": r["name"]} for r in item["results"]]
            elif kind == "assistant" and item["final"] and item["text"]:  # réponse du cloud
                body.append({"role": "assistant", "content": item["text"]})
        if len(body) > max_messages:
            body = body[-max_messages:]
            while body and body[0]["role"] not in ("user", "system"):
                body.pop(0)  # ne jamais commencer par une réponse d'outil orpheline
        return [{"role": "system", "content": system_prompt}] + body

    # --- affichage (overlay, CLI) ---------------------------------------------
    def transcript(self) -> list[dict]:
        out: list[dict] = []
        for item in self.items:
            if item["kind"] == "user":
                out.append({"role": "user", "text": item["text"]})
            elif item["kind"] == "assistant" and item["text"]:
                out.append({"role": "assistant", "text": item["text"], "backend": item["backend"]})
            elif item["kind"] == "tools":
                out += [{"role": "tool", "text": r.get("label") or r["name"], "ok": r["ok"]} for r in item["results"]]
        return out


def _claude_tool_result(result: dict) -> dict:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": result["id"]}
    if result.get("image"):
        block["content"] = [
            {"type": "image", "source": {"type": "base64", "media_type": result.get("image_type", "image/jpeg"),
                                         "data": base64.standard_b64encode(result["image"]).decode("ascii")}},
            {"type": "text", "text": result["content"]},
        ]
    else:
        block["content"] = result["content"]
    if not result["ok"]:
        block["is_error"] = True
    return block
