"""Outils « logiciels » : rechercher, installer, mettre à jour (pacman + snapshots)."""
from __future__ import annotations

import re

from ..schema import obj
from . import Tool, ToolContext, ToolResult

PACKAGE_NAME = re.compile(r"^[a-z0-9@._+][a-z0-9@._+-]{0,99}$")


def search_packages(args: dict, ctx: ToolContext) -> ToolResult:
    query = args["query"].strip()
    result = ctx.runner.run(["pacman", "-Ss", "--", query], timeout=20)
    if result.returncode == 1 and not result.stdout:
        return ToolResult(True, f"Aucun logiciel trouvé pour « {query} » dans les dépôts.")
    if not result.ok:
        return ToolResult(False, f"Recherche impossible : {result.stderr.strip()}")
    entries, lines = [], result.stdout.splitlines()
    for index, line in enumerate(lines):
        if line and not line.startswith(" "):
            description = lines[index + 1].strip() if index + 1 < len(lines) else ""
            installed = " [installé]" if "[installed" in line or "[installé" in line else ""
            name = line.split(" [")[0]
            entries.append(f"{name}{installed} — {description}")
    return ToolResult(True, "\n".join(entries[:12]) or "Aucun résultat.")


def install_packages(args: dict, ctx: ToolContext) -> ToolResult:
    packages = [p.strip() for p in args["packages"] if p.strip()]
    bad = [p for p in packages if not PACKAGE_NAME.match(p)]
    if not packages or bad:
        return ToolResult(False, f"Nom de paquet invalide : {', '.join(bad) or '(vide)'}")
    ctx.emit({"type": "progress", "text": f"Installation de {', '.join(packages)}… (un instantané du système est créé avant)"})
    result = ctx.runner.run(["pkexec", "pacman", "-S", "--needed", "--noconfirm", *packages], timeout=1800)
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-12:])
    if result.returncode in (126, 127):
        return ToolResult(False, "Installation annulée (mot de passe administrateur refusé).")
    if not result.ok:
        return ToolResult(False, f"Échec de l'installation :\n{tail}")
    return ToolResult(True, f"Installé : {', '.join(packages)}.\n{tail}")


def update_system(args: dict, ctx: ToolContext) -> ToolResult:
    if ctx.runner.spawn(["nova-terminal", "--title=Mise à jour de Nova OS", "-e", "nova-update"]):
        return ToolResult(True, "La mise à jour a démarré dans un terminal (un instantané est créé avant, "
                                "pour pouvoir revenir en arrière depuis le menu de démarrage).")
    return ToolResult(False, "Impossible d'ouvrir le terminal de mise à jour.")


TOOLS = [
    Tool("search_packages",
         "Search the software repositories (pacman) for programs to install.",
         obj({"query": {"type": "string"}}, ["query"]),
         search_packages, "read", label=lambda a: f"Recherche de logiciels « {a.get('query', '')} »"),
    Tool("install_packages",
         "Install software packages from the official repositories with pacman (exact package "
         "names, use search_packages first if unsure). A system snapshot is taken automatically.",
         obj({
             "packages": {"type": "array", "items": {"type": "string"}, "description": "Exact package names"},
             "reason": {"type": "string", "description": "Why, in the user's language"},
         }, ["packages", "reason"]),
         install_packages, "sensitive",
         label=lambda a: f"Installation de {', '.join(a.get('packages', []))}",
         summary=lambda a: f"Installer : {', '.join(a.get('packages', []))}\nRaison : {a.get('reason', '')}"),
    Tool("update_system",
         "Update the whole system (opens a terminal running the Nova updater, with snapshot).",
         obj({}), update_system, "sensitive", label=lambda a: "Mise à jour du système",
         summary=lambda a: "Lancer la mise à jour complète du système"),
]
