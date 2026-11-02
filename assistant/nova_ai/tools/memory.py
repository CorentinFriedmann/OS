"""Mémoire à long terme de Nova (préférences, faits à retenir), stockée localement."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..config import data_dir
from ..schema import obj
from . import Tool, ToolContext, ToolResult
from .desktop import normalize

MAX_FACTS = 200


def memory_file(ctx: ToolContext | None = None) -> Path:
    base = ctx.data_dir if ctx and ctx.data_dir else data_dir()
    return base / "memory.json"


def load_facts(path: Path) -> list[dict]:
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
        return facts if isinstance(facts, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_facts(path: Path, facts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(facts[-MAX_FACTS:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def remember(args: dict, ctx: ToolContext) -> ToolResult:
    fact = args["fact"].strip()
    if not fact:
        return ToolResult(False, "Rien à retenir.")
    path = memory_file(ctx)
    facts = load_facts(path)
    if any(normalize(f.get("text", "")) == normalize(fact) for f in facts):
        return ToolResult(True, "Je le savais déjà.")
    facts.append({"id": int(time.time() * 1000), "text": fact, "date": time.strftime("%Y-%m-%d")})
    save_facts(path, facts)
    return ToolResult(True, "C'est noté, je m'en souviendrai.")


def recall(args: dict, ctx: ToolContext) -> ToolResult:
    facts = load_facts(memory_file(ctx))
    query = normalize(args.get("query", ""))
    hits = [f for f in facts if query in normalize(f.get("text", ""))] if query else facts
    if not hits:
        return ToolResult(True, "Je n'ai rien retenu à ce sujet.")
    return ToolResult(True, "\n".join(f"- {f['text']} ({f.get('date', '')})" for f in hits[-30:]))


def forget(args: dict, ctx: ToolContext) -> ToolResult:
    path = memory_file(ctx)
    facts = load_facts(path)
    query = normalize(args["query"])
    kept = [f for f in facts if query not in normalize(f.get("text", ""))]
    save_facts(path, kept)
    removed = len(facts) - len(kept)
    return ToolResult(True, f"{removed} souvenir(s) effacé(s)." if removed else "Rien à effacer.")


def recent_facts(limit: int = 15, path: Path | None = None) -> list[str]:
    return [f["text"] for f in load_facts(path or memory_file())[-limit:] if f.get("text")]


TOOLS = [
    Tool("remember",
         "Save a lasting fact about the user or their preferences (name, habits, projects, likes). "
         "Call it when the user says 'souviens-toi', 'retiens', 'remember', or shares a stable preference.",
         obj({"fact": {"type": "string", "description": "The fact, as a short sentence in the user's language"}}, ["fact"]),
         remember, "action", label=lambda a: "Mémorisation"),
    Tool("recall", "Search what you previously saved about the user.",
         obj({"query": {"type": "string", "description": "Keyword (empty = everything)"}}),
         recall, "read", label=lambda a: "Recherche dans la mémoire"),
    Tool("forget", "Delete saved facts containing a text, when the user asks you to forget something.",
         obj({"query": {"type": "string"}}, ["query"]),
         forget, "action", label=lambda a: "Oubli d'un souvenir"),
]
