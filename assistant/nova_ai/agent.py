"""Boucle de l'agent Nova, commune aux moteurs local et cloud.

Pour chaque demande : choix du moteur (router), génération en streaming,
exécution des outils demandés (avec validation et confirmation si besoin),
puis nouvelle génération jusqu'à la réponse finale.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from . import router
from .backends import Backend, BackendError, Cancelled, ToolCall
from .backends.claude import ClaudeBackend, default_base_url
from .backends.ollama import OllamaBackend
from .config import data_dir as default_data_dir
from .config import get_api_key
from .conversation import Conversation
from .persona import build_context
from .runner import Runner
from .tools import Registry, ToolContext, ToolResult, default_registry
from .tools.memory import recent_facts

Emit = Callable[[dict], None]
Confirm = Callable[[dict], bool]


class Agent:
    MAX_STEPS = 10

    def __init__(self, config: dict, registry: Registry | None = None, runner: Runner | None = None,
                 backends: dict[str, Backend] | None = None, data_dir: Path | None = None):
        self.config = config
        self.registry = registry or default_registry()
        self.runner = runner or Runner()
        self.data_dir = data_dir or default_data_dir()
        self.backends: dict[str, Backend] = backends or {
            "local": OllamaBackend(config),
            "cloud": ClaudeBackend(config, get_api_key(), default_base_url()),
        }
        self.conversation = Conversation()
        self._lock = threading.Lock()

    # --- état ------------------------------------------------------------------
    def availability(self) -> dict:
        out = {}
        for name, backend in self.backends.items():
            ok, why = backend.available()
            out[name] = {"ok": ok, "reason": why, "model": backend.model}
        return out

    def reset(self) -> None:
        self.conversation = Conversation()

    def _maybe_reset(self) -> None:
        settings = self.config.get("conversation", {})
        conv = self.conversation
        if conv.items and (conv.idle_minutes() > settings.get("idle_reset_minutes", 20)
                           or conv.exchanges() >= settings.get("max_exchanges", 40)):
            self.reset()

    # --- une demande de l'utilisateur ----------------------------------------------
    def ask(self, text: str, emit: Emit, confirm: Confirm, cancel: threading.Event | None = None,
            mode: str | None = None) -> str:
        """Traite une demande (bloquant : à appeler dans un thread). Retourne le texte final."""
        cancel = cancel or threading.Event()
        with self._lock:
            self._maybe_reset()
            config = self.config if mode is None else {**self.config, "mode": mode}
            local_ok, local_why = self.backends["local"].available()
            cloud_ok, cloud_why = self.backends["cloud"].available()
            conv = self.conversation
            decision = router.choose(text, config, local_ok, cloud_ok,
                                     conv.last_backend(), time.time() - conv.updated)
            if decision.backend == "local" and not local_ok:
                message = local_why if not cloud_ok else f"{local_why} {cloud_why}"
                if config.get("privacy", {}).get("strict_local"):
                    message = f"{local_why} (le mode confidentialité stricte interdit le cloud)."
                emit({"type": "error", "message": message.strip()})
                return ""
            backend = self.backends[decision.backend]
            facts = recent_facts(path=self.data_dir / "memory.json")
            context = build_context(self.runner, backend.name, backend.model, facts,
                                    web_search=backend.name == "cloud" and self.config["cloud"].get("web_search", True))
            conv.add_user(decision.text, context)
            emit({"type": "turn_start", "backend": backend.name, "model": backend.model, "reason": decision.reason})
            return self._loop(backend, emit, confirm, cancel)

    def _loop(self, backend: Backend, emit: Emit, confirm: Confirm, cancel: threading.Event) -> str:
        conv = self.conversation
        tools = self.registry.for_backend(backend.name)
        ctx = ToolContext(runner=self.runner, config=self.config, backend=backend.name,
                          data_dir=self.data_dir, emit=emit)
        final_text, usage = "", {}
        try:
            for _ in range(self.MAX_STEPS):
                step = backend.step(conv, tools, emit, cancel)
                usage = step.usage or usage
                paused = step.stop_reason == "pause_turn"
                done = not paused and (not step.tool_calls or step.stop_reason in ("refusal", "max_tokens"))
                conv.add_assistant(backend.name, step.text, [asdict(c) for c in step.tool_calls],
                                   raw=step.raw, model=step.model, final=done and not step.tool_calls)
                if step.notice:
                    emit({"type": "notice", "text": step.notice})
                if paused:
                    continue  # recherche web côté serveur : on relance, Claude reprend seul
                if done:
                    if step.tool_calls:
                        # Refus ou réponse coupée au milieu d'un appel d'outil : on n'exécute
                        # rien, mais chaque appel reçoit une réponse pour garder l'historique valide.
                        if step.stop_reason == "max_tokens":
                            emit({"type": "error", "message": "Réponse tronquée (trop longue) : reformule plus simplement."})
                        self._close_turn(backend.name, "(interrompu)")
                    final_text = step.text
                    break
                results = [self._run_tool(call, backend.name, ctx, emit, confirm, cancel) for call in step.tool_calls]
                conv.add_tool_results(backend.name, results)
            else:
                emit({"type": "error", "message": "Trop d'étapes pour cette demande : j'arrête ici."})
                conv.add_assistant(backend.name, "(arrêt : trop d'étapes)", final=True)
        except Cancelled:
            self._close_turn(backend.name, "(réponse interrompue)")
            emit({"type": "notice", "text": "Réponse interrompue."})
        except BackendError as error:
            self._close_turn(backend.name, "(erreur)")
            emit({"type": "error", "message": str(error)})
        emit({"type": "turn_end", "backend": backend.name, "text": final_text, "usage": usage})
        return final_text

    def _close_turn(self, backend: str, text: str) -> None:
        """Termine proprement l'échange après une erreur, pour garder un historique valide."""
        conv = self.conversation
        last = conv.items[-1] if conv.items else None
        if last and last["kind"] == "assistant" and last["tool_calls"]:
            # des outils étaient demandés : chaque appel doit recevoir une réponse
            conv.add_tool_results(backend, [
                {"id": c["id"], "name": c["name"], "label": c["name"], "ok": False, "content": "Action annulée."}
                for c in last["tool_calls"]
            ])
        conv.add_assistant(backend, text, final=True)

    # --- exécution d'un outil ---------------------------------------------------------
    def _run_tool(self, call: ToolCall, backend: str, ctx: ToolContext, emit: Emit,
                  confirm: Confirm, cancel: threading.Event) -> dict:
        tool = self.registry.get(call.name)
        base = {"id": call.id, "name": call.name, "label": call.name}
        if cancel.is_set():
            return {**base, "ok": False, "content": "Action annulée par l'utilisateur."}
        if tool is None or (tool.cloud_only and backend == "local"):
            return {**base, "ok": False, "content": f"Outil inconnu : {call.name}"}
        if not isinstance(call.arguments, dict):
            payload = json.dumps({"INVALID_JSON": json.dumps(call.arguments, ensure_ascii=False)}, ensure_ascii=False)
            return {**base, "ok": False, "content": payload}
        errors = self.registry.validate(tool, call.arguments)
        if errors:
            return {**base, "ok": False, "content": "Arguments invalides : " + "; ".join(errors)}
        label = tool.describe(call.arguments)
        base["label"] = label
        if Registry.needs_confirmation(tool, backend, self.config):
            approved = confirm({
                "type": "confirm", "id": call.id, "tool": tool.name, "label": label,
                "summary": tool.confirmation_text(call.arguments), "risk": tool.risk,
            })
            if not approved:
                emit({"type": "tool_end", "id": call.id, "ok": False, "label": label, "denied": True})
                return {**base, "ok": False,
                        "content": "L'utilisateur a refusé cette action. Ne la retente pas sans sa demande."}
        emit({"type": "tool_start", "id": call.id, "name": tool.name, "label": label})
        try:
            result = tool.handler(call.arguments, ctx)
        except Exception as error:  # noqa: BLE001 - un outil défaillant ne doit pas faire tomber Nova
            result = ToolResult(False, f"Erreur interne de l'outil : {error}")
        emit({"type": "tool_end", "id": call.id, "ok": result.ok, "label": label})
        return {**base, "ok": result.ok, "content": result.content,
                "image": result.image, "image_type": result.image_type}
