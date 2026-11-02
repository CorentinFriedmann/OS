"""Outil « commande » : dernier recours, toujours confirmé par l'utilisateur."""
from __future__ import annotations

import re

from ..schema import obj
from . import Tool, ToolContext, ToolResult

MAX_OUTPUT = 6000

# Refusées dans tous les cas : elles détruisent le système sans retour possible.
BLOCKED = [
    (re.compile(r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)[a-z]*\s+(--no-preserve-root\s+)?(/|/\*|~|~/|\$HOME/?)(\s|$)"),
     "suppression de tout le système ou du dossier personnel"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"), "bombe fork"),
    (re.compile(r"\bmkfs(\.\w+)?\s+/dev/(sd|nvme|vd|mmcblk)"), "formatage d'un disque"),
    (re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|vd|mmcblk)"), "écriture brute sur un disque"),
    (re.compile(r">\s*/dev/(sd|nvme|vd|mmcblk)\w*"), "écriture brute sur un disque"),
]
# Autorisées mais signalées en rouge dans la demande de confirmation.
RISKY = re.compile(
    r"\b(rm|rmdir|shred|chmod|chown|mv|dd|truncate|systemctl\s+(stop|disable|mask)|"
    r"pacman\s+-R|userdel|passwd|reboot|poweroff|shutdown|kill|pkill|killall)\b"
)


def check_command(command: str) -> tuple[bool, str]:
    for pattern, reason in BLOCKED:
        if pattern.search(command):
            return False, reason
    return True, ""


def is_risky(command: str) -> bool:
    return bool(RISKY.search(command))


def run_command(args: dict, ctx: ToolContext) -> ToolResult:
    command = args["command"].strip()
    allowed, reason = check_command(command)
    if not allowed:
        return ToolResult(False, f"Commande refusée par Nova ({reason}). Propose une alternative sûre.")
    argv = ["bash", "-lc", command]
    if args.get("as_root"):
        argv = ["pkexec", "bash", "-c", command]  # mot de passe demandé par la fenêtre polkit
    result = ctx.runner.run(argv, timeout=180)
    output = (result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")).strip()
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + f"\n[… sortie tronquée ({len(output)} caractères)]"
    return ToolResult(result.ok, f"Code de retour : {result.returncode}\n{output or '(aucune sortie)'}")


def _summary(args: dict) -> str:
    command = args.get("command", "")
    prefix = "⚠ Commande potentiellement destructrice. " if is_risky(command) else ""
    root = " (en administrateur)" if args.get("as_root") else ""
    why = f"\nRaison : {args['reason']}" if args.get("reason") else ""
    return f"{prefix}Exécuter{root} :\n{command}{why}"


TOOLS = [
    Tool("run_command",
         "Run a shell command (bash) on the user's computer and get its output. Use it only when no "
         "dedicated tool fits. The user always sees and must approve the exact command. Set "
         "as_root only when administrator rights are truly required (a password prompt appears).",
         obj({
             "command": {"type": "string", "description": "The exact bash command"},
             "reason": {"type": "string", "description": "Short explanation, in the user's language"},
             "as_root": {"type": "boolean", "description": "Run with administrator rights"},
         }, ["command", "reason"]),
         run_command, "sensitive", label=lambda a: "Exécution d'une commande", summary=_summary),
]
