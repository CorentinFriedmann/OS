"""Moteurs d'IA de Nova : local (Ollama) et cloud (Claude)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

Emit = Callable[[dict], None]


class BackendError(Exception):
    """Erreur affichable telle quelle à l'utilisateur (en français)."""


class Cancelled(Exception):
    """L'utilisateur a interrompu la réponse."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Any  # dict attendu, mais à valider : c'est une sortie de modèle


@dataclass
class StepResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw: list[dict] | None = None  # contenu brut (Claude), renvoyé tel quel ensuite
    model: str = ""
    usage: dict = field(default_factory=dict)
    notice: str = ""  # information à afficher (repli de modèle, refus…)


class Backend(Protocol):
    name: str
    model: str

    def available(self) -> tuple[bool, str]: ...

    def step(self, conversation, tools: list, emit: Emit, cancel) -> StepResult: ...
