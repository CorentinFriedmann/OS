"""Outils « fichiers » : recherche et lecture de fichiers texte (avec garde-fous)."""
from __future__ import annotations

import os
from pathlib import Path

from ..schema import obj
from . import Tool, ToolContext, ToolResult

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CHARS = 20000

# Jamais lus, même sur demande : clés, mots de passe, trousseaux…
FORBIDDEN = (
    ".ssh", ".gnupg", ".password-store", ".local/share/keyrings", ".config/nova/secrets.env",
    ".mozilla/firefox", ".config/chromium", ".config/google-chrome", ".config/BraveSoftware",
    ".aws", ".kube", ".docker/config.json", ".netrc", ".git-credentials",
)
ALLOWED_ROOTS = ("/etc", "/usr/share/doc", "/tmp", "/var/log")


def resolve_safe_path(raw: str, home: Path) -> tuple[Path | None, str]:
    path = Path(os.path.expanduser(raw.strip()))
    if not path.is_absolute():
        path = home / path
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, f"Le fichier {raw} n'existe pas."
    home = home.resolve()
    inside_home = path.is_relative_to(home)
    if not inside_home and not any(path.is_relative_to(root) for root in ALLOWED_ROOTS):
        return None, "Pour ta sécurité, je ne lis que les fichiers de ton dossier personnel et de /etc."
    if inside_home:
        relative = path.relative_to(home).as_posix()
        if any(relative == f or relative.startswith(f + "/") for f in FORBIDDEN):
            return None, "Ce fichier contient des secrets (clés, mots de passe) : je ne le lis pas."
    return path, ""


def read_text_file(args: dict, ctx: ToolContext) -> ToolResult:
    path, error = resolve_safe_path(args["path"], ctx.home)
    if path is None:
        return ToolResult(False, error)
    if path.is_dir():
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())[:200]
        return ToolResult(True, f"{path} est un dossier :\n" + "\n".join(entries))
    if path.stat().st_size > MAX_FILE_BYTES:
        return ToolResult(False, "Fichier trop volumineux (plus de 2 Mo).")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return ToolResult(False, "C'est un fichier binaire, pas un fichier texte.")
    text = data.decode("utf-8", errors="replace")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n[… tronqué : {len(text) - MAX_CHARS} caractères de plus]"
    return ToolResult(True, text)


def search_files(args: dict, ctx: ToolContext) -> ToolResult:
    query = args["query"].strip()
    if not query:
        return ToolResult(False, "Que faut-il chercher ?")
    kind = args.get("kind", "any")
    limit = max(1, min(int(args.get("limit", 20)), 50))
    home = str(ctx.home)
    if ctx.runner.which("fd"):
        argv = ["fd", "--ignore-case", "--max-results", str(limit)]
        argv += {"file": ["--type", "f"], "folder": ["--type", "d"]}.get(kind, [])
        argv += ["--", query, home]
    else:
        argv = ["find", home, "-maxdepth", "7", "-not", "-path", "*/.*"]
        argv += {"file": ["-type", "f"], "folder": ["-type", "d"]}.get(kind, [])
        argv += ["-iname", f"*{query}*"]
    result = ctx.runner.run(argv, timeout=20)
    lines = [line.replace(home, "~", 1) for line in result.stdout.splitlines() if line.strip()][:limit]
    if not lines:
        return ToolResult(True, f"Aucun fichier ne correspond à « {query} ».")
    return ToolResult(True, "\n".join(lines))


TOOLS = [
    Tool("search_files",
         "Search the user's home folder for files or folders whose name contains a text. "
         "Call this when the user looks for a document, photo, download, project, etc.",
         obj({
             "query": {"type": "string", "description": "Part of the file or folder name"},
             "kind": {"type": "string", "enum": ["any", "file", "folder"]},
             "limit": {"type": "integer", "description": "Maximum results, 1-50 (default 20)"},
         }, ["query"]),
         search_files, "read", label=lambda a: f"Recherche de « {a.get('query', '')} »"),
    Tool("read_text_file",
         "Read a text file (or list a folder) from the user's home folder or /etc, to summarize, "
         "explain or fix it. Secrets (SSH keys, passwords) are never readable.",
         obj({"path": {"type": "string", "description": "Path, e.g. ~/Documents/notes.txt"}}, ["path"]),
         read_text_file, "private", label=lambda a: f"Lecture de {a.get('path', '')}",
         summary=lambda a: f"Envoyer le contenu de {a.get('path', '')} à Claude (cloud)"),
]
