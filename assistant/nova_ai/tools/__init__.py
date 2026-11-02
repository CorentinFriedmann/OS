"""Outils que Nova peut utiliser pour agir sur l'ordinateur.

Niveaux de risque :
  read       lecture d'informations sans conséquence (état du système…)
  action     action courante et réversible (ouvrir une appli, régler le son…)
  private    lit des données personnelles (fichier, écran, presse-papiers) :
             confirmation demandée si elles partent vers le cloud
  sensitive  modifie le système (commande shell, installation…) :
             toujours confirmée par défaut
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..runner import Runner
from ..schema import validate

RISKS = ("read", "action", "private", "sensitive")


@dataclass
class ToolResult:
    ok: bool
    content: str
    image: bytes | None = None
    image_type: str = "image/jpeg"


@dataclass
class ToolContext:
    runner: Runner
    config: dict
    backend: str = "local"  # "local" ou "cloud"
    home: Path = field(default_factory=Path.home)
    data_dir: Path | None = None
    emit: Callable[[dict], None] = lambda event: None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], ToolResult]
    risk: str = "read"
    label: Callable[[dict], str] = lambda args: ""
    summary: Callable[[dict], str] | None = None
    cloud_only: bool = False

    def __post_init__(self) -> None:
        if self.risk not in RISKS:
            raise ValueError(f"risque inconnu : {self.risk}")

    def describe(self, args: dict) -> str:
        """Phrase affichée à l'utilisateur (« Ouverture de Firefox »)."""
        try:
            return self.label(args) or self.name
        except Exception:  # noqa: BLE001 - un libellé ne doit jamais casser l'agent
            return self.name

    def confirmation_text(self, args: dict) -> str:
        if self.summary:
            try:
                return self.summary(args)
            except Exception:  # noqa: BLE001
                pass
        return self.describe(args)


class Registry:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.name: tool for tool in tools}

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def for_backend(self, backend: str) -> list[Tool]:
        return [t for t in self._tools.values() if backend == "cloud" or not t.cloud_only]

    def validate(self, tool: Tool, args: Any) -> list[str]:
        return validate(args, tool.parameters)

    @staticmethod
    def needs_confirmation(tool: Tool, backend: str, config: dict) -> bool:
        confirm = config.get("confirm", {})
        if tool.risk == "sensitive":
            return confirm.get("sensitive", "always") != "never"
        if tool.risk == "action":
            return confirm.get("action", "never") == "always"
        if tool.risk == "private":
            return backend == "cloud" and config.get("privacy", {}).get("confirm_private_in_cloud", True)
        return False


def default_registry() -> Registry:
    from . import desktop, files, memory, packages, shell, system

    tools: list[Tool] = []
    for module in (system, desktop, files, memory, packages, shell):
        tools += module.TOOLS
    return Registry(tools)
