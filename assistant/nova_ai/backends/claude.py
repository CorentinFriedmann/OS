"""Moteur cloud : Claude, via le SDK officiel « anthropic ».

Choix techniques (doc Anthropic à jour) :
- streaming de bout en bout, avec `eager_input_streaming` + validation locale
  des arguments d'outils ;
- outils en mode `strict` (arguments conformes au schéma) ;
- recherche web côté serveur (`web_search_20260209`), reprise sur `pause_turn` ;
- repli automatique côté serveur en cas de refus (`fallbacks: "default"`) ;
- cache du préfixe (outils + consignes) via `cache_control` ;
- historique en ajout seul : les blocs renvoyés par Claude sont réutilisés tels quels.
"""
from __future__ import annotations

import os
import threading

from ..config import DEFAULT_CLOUD_MODEL
from ..persona import SYSTEM_PROMPT
from . import BackendError, Cancelled, Emit, StepResult, ToolCall

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Modèles acceptant un message « system » en cours de conversation
SYSTEM_MESSAGE_MODELS = ("claude-opus-5", "claude-opus-4-8", "claude-fable-5", "claude-mythos-5",
                         "claude-sonnet-5-5", "claude-haiku-5-5")
# Repli serveur disponible (pas pour Haiku 5.5)
FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")
ADAPTIVE_THINKING_MODELS = ("claude-opus-5", "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8",
                            "claude-fable-5", "claude-mythos-5", "claude-sonnet-5", "claude-sonnet-4-6",
                            "claude-haiku-5-5")
NO_EFFORT_MODELS = ("claude-haiku-4-5", "claude-sonnet-4-5")
WEB_SEARCH_DYNAMIC = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                      "claude-sonnet-5", "claude-sonnet-4-6")


def system_timezone() -> str | None:
    try:
        target = os.readlink("/etc/localtime")
    except OSError:
        return None
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else None


class ClaudeBackend:
    name = "cloud"

    def __init__(self, config: dict, api_key: str | None, base_url: str | None = None):
        cloud = config["cloud"]
        self.model = cloud.get("model") or DEFAULT_CLOUD_MODEL
        self.effort = cloud.get("effort", "medium")
        self.max_tokens = int(cloud.get("max_tokens", 64000))
        self.web_search = bool(cloud.get("web_search", True))
        self.api_key = api_key
        self.base_url = base_url
        self._client = None

    # --- client ------------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as error:
                raise BackendError("Le module « anthropic » est absent : réinstalle le paquet nova-assistant.") from error
            kwargs = {"api_key": self.api_key, "max_retries": 2}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "Aucune clé API Claude configurée (lance « nova setup »)."
        return True, ""

    @property
    def supports_system_messages(self) -> bool:
        return self.model.startswith(SYSTEM_MESSAGE_MODELS)

    # --- requête -----------------------------------------------------------------
    def tool_definitions(self, tools: list) -> list[dict]:
        definitions: list[dict] = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
            "strict": True,
            "eager_input_streaming": True,
        } for tool in tools]
        if self.web_search:
            search: dict = {
                "type": "web_search_20260209" if self.model.startswith(WEB_SEARCH_DYNAMIC) else "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,
            }
            timezone = system_timezone()
            search["user_location"] = {"type": "approximate", "country": "FR",
                                       **({"timezone": timezone} if timezone else {})}
            definitions.append(search)
        return definitions

    def build_params(self, conversation, tools: list) -> dict:
        params: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": SYSTEM_PROMPT}],
            "messages": conversation.to_claude(self.supports_system_messages),
            "tools": self.tool_definitions(tools),
            "cache_control": {"type": "ephemeral"},
        }
        if self.model.startswith(ADAPTIVE_THINKING_MODELS):
            params["thinking"] = {"type": "adaptive"}
        if not self.model.startswith(NO_EFFORT_MODELS):
            params["output_config"] = {"effort": self.effort}
        if self.model.startswith(FALLBACK_MODELS):
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    # --- un tour de génération -------------------------------------------------------
    def step(self, conversation, tools: list, emit: Emit, cancel: threading.Event) -> StepResult:
        import anthropic

        params = self.build_params(conversation, tools)
        retries = 0
        while True:
            try:
                final = self._stream(params, emit, cancel)
                break
            except anthropic.AuthenticationError as error:
                raise BackendError("Clé API Claude invalide ou révoquée (lance « nova setup »).") from error
            except anthropic.PermissionDeniedError as error:
                raise BackendError("Cette clé API n'a pas accès à ce modèle Claude.") from error
            except anthropic.RateLimitError as error:
                raise BackendError("Trop de requêtes vers Claude pour l'instant : réessaie dans une minute.") from error
            except anthropic.BadRequestError as error:
                raise BackendError(f"Requête refusée par l'API Claude : {error.message}") from error
            except anthropic.APIStatusError as error:
                raise BackendError(f"Le service Claude a rencontré une erreur ({error.status_code}).") from error
            except anthropic.APIConnectionError as error:
                raise BackendError("Pas de connexion à internet (ou l'API Claude est injoignable).") from error
            except ValueError as error:
                # Arguments d'outil en JSON illisible : le SDK lève avant la fin du bloc,
                # il n'y a pas d'identifiant d'outil à qui répondre -> on relance le tour.
                retries += 1
                if retries > 2:
                    raise BackendError("Claude a produit une réponse illisible, réessaie.") from error
                emit({"type": "progress", "text": "Nouvel essai…"})

        content = list(final.content)
        text = "".join(block.text for block in content if block.type == "text")
        calls = [ToolCall(block.id, block.name, block.input) for block in content if block.type == "tool_use"]
        notice = ""
        if any(block.type == "fallback" for block in content):
            notice = f"Réponse fournie par le modèle de repli {final.model}."
        if final.stop_reason == "refusal":
            notice = "Claude a décliné cette demande."
        usage = {
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "cache_read_input_tokens": getattr(final.usage, "cache_read_input_tokens", 0) or 0,
        }
        return StepResult(
            text=text, tool_calls=calls, stop_reason=final.stop_reason or "end_turn",
            raw=[block.to_dict(mode="json") for block in content],
            model=final.model, usage=usage, notice=notice,
        )

    def _stream(self, params: dict, emit: Emit, cancel: threading.Event):
        with self.client.beta.messages.stream(**params) as stream:
            for event in stream:
                if cancel.is_set():
                    raise Cancelled()
                if event.type == "text":
                    emit({"type": "text", "text": event.text})
                elif event.type == "content_block_start":
                    block = event.content_block
                    if block.type in ("thinking", "redacted_thinking"):
                        emit({"type": "thinking"})
                    elif block.type == "server_tool_use":
                        emit({"type": "web_search", "name": block.name})
                    elif block.type == "tool_use":
                        emit({"type": "tool_prepare", "name": block.name})
            return stream.get_final_message()


def default_base_url() -> str | None:
    """Permet de pointer vers un serveur de test (NOVA_CLAUDE_BASE_URL)."""
    return os.environ.get("NOVA_CLAUDE_BASE_URL") or None


__all__ = ["ClaudeBackend", "default_base_url"]
