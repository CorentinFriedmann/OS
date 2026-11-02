"""Tests de bout en bout des moteurs contre des serveurs locaux scriptés.

- Claude : le vrai SDK `anthropic` parle à un faux serveur qui renvoie des flux
  SSE conformes à l'API (réflexion, appels d'outils, recherche web, refus).
- Ollama : faux serveur NDJSON conforme à /api/chat.
"""
from __future__ import annotations

import json
import threading

import pytest

from nova_ai.agent import Agent
from nova_ai.backends.claude import ClaudeBackend
from nova_ai.backends.ollama import OllamaBackend
from nova_ai.runner import Completed
from tests.conftest import FakeRunner, ScriptedServer

anthropic = pytest.importorskip("anthropic")


# --- fabrique de flux SSE Claude -------------------------------------------------------
def sse(blocks: list[dict], stop_reason: str, model: str = "claude-opus-5-5") -> str:
    events = [("message_start", {"type": "message_start", "message": {
        "id": "msg_test", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 1, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}}})]
    for index, block in enumerate(blocks):
        kind = block["type"]
        if kind == "text":
            events.append(("content_block_start", {"type": "content_block_start", "index": index,
                                                   "content_block": {"type": "text", "text": ""}}))
            for start in range(0, len(block["text"]), 7):
                events.append(("content_block_delta", {"type": "content_block_delta", "index": index,
                                                       "delta": {"type": "text_delta", "text": block["text"][start:start + 7]}}))
        elif kind == "thinking":
            events.append(("content_block_start", {"type": "content_block_start", "index": index,
                                                   "content_block": {"type": "thinking", "thinking": "", "signature": ""}}))
            events.append(("content_block_delta", {"type": "content_block_delta", "index": index,
                                                   "delta": {"type": "signature_delta", "signature": block["signature"]}}))
        elif kind in ("tool_use", "server_tool_use"):
            events.append(("content_block_start", {"type": "content_block_start", "index": index,
                                                   "content_block": {"type": kind, "id": block["id"], "name": block["name"], "input": {}}}))
            events.append(("content_block_delta", {"type": "content_block_delta", "index": index,
                                                   "delta": {"type": "input_json_delta", "partial_json": block["json"]}}))
        else:  # bloc livré d'un coup (résultat de recherche web…)
            events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": block}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                     "usage": {"output_tokens": 42}}))
    events.append(("message_stop", {"type": "message_stop"}))
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def claude_handler(server, handler, method, body):
    if not server.responses:
        handler.send_response(500)
        handler.end_headers()
        return
    status, payload = server.responses.pop(0)
    data = payload.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/event-stream" if status == 200 else "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


@pytest.fixture
def claude_server():
    server = ScriptedServer(claude_handler)
    yield server
    server.close()


class Recorder:
    def __init__(self, approve=True):
        self.events: list[dict] = []
        self.confirmations: list[dict] = []
        self.approve = approve

    def emit(self, event):
        self.events.append(event)

    def confirm(self, request):
        self.confirmations.append(request)
        return self.approve

    def types(self):
        return [e["type"] for e in self.events]

    def text(self):
        return "".join(e["text"] for e in self.events if e["type"] == "text")


class DownLocal:
    name, model = "local", "qwen3:4b"

    def available(self):
        return False, "IA locale arrêtée"


def make_cloud_agent(config, server, runner):
    config["cloud"]["web_search"] = True
    backend = ClaudeBackend(config, api_key="sk-ant-test", base_url=server.url)
    return Agent(config, runner=runner, backends={"local": DownLocal(), "cloud": backend})


def test_claude_tool_loop_end_to_end(config, claude_server):
    runner = FakeRunner({("wpctl", "get-volume"): Completed(0, "Volume: 0.60\n", "")})
    claude_server.responses = [
        (200, sse([{"type": "thinking", "signature": "c2lnbmF0dXJl"},
                   {"type": "text", "text": "Je monte le son."},
                   {"type": "tool_use", "id": "toolu_01", "name": "volume", "json": '{"action": "up", "percent": 10}'}],
                  "tool_use")),
        (200, sse([{"type": "text", "text": "C'est fait, le volume est à 60 %."}], "end_turn")),
    ]
    agent = make_cloud_agent(config, claude_server, runner)
    rec = Recorder()
    final = agent.ask("monte le son", rec.emit, rec.confirm)

    assert final == "C'est fait, le volume est à 60 %."
    assert ["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "10%+"] in runner.calls
    assert rec.types()[0] == "turn_start" and "thinking" in rec.types() and "tool_end" in rec.types()
    assert rec.text() == "Je monte le son.C'est fait, le volume est à 60 %."

    first, second = (r["body"] for r in claude_server.requests)
    headers = claude_server.requests[0]["headers"]
    # Paramètres recommandés par la doc Anthropic
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in headers.get("anthropic-beta", "")
    assert first["cache_control"] == {"type": "ephemeral"}
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "medium"}
    assert first["stream"] is True
    volume = next(t for t in first["tools"] if t.get("name") == "volume")
    assert volume["strict"] is True and volume["eager_input_streaming"] is True
    search = next(t for t in first["tools"] if t.get("type", "").startswith("web_search"))
    assert search["type"] == "web_search_20260209" and "eager_input_streaming" not in search
    assert first["messages"][0] == {"role": "user", "content": "monte le son"}
    assert first["messages"][1]["role"] == "system" and "Contexte actuel" in first["messages"][1]["content"]
    # Second appel : historique en ajout seul, bloc de réflexion renvoyé intact
    assert second["messages"][:2] == first["messages"]
    replay = second["messages"][2]
    assert replay["role"] == "assistant"
    assert replay["content"][0]["type"] == "thinking" and replay["content"][0]["signature"] == "c2lnbmF0dXJl"
    assert replay["content"][2]["input"] == {"action": "up", "percent": 10}
    result = second["messages"][3]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_01" and "60" in result["content"]


def test_claude_pause_turn_is_resumed(config, claude_server):
    runner = FakeRunner()
    search_result = {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1",
                     "content": [{"type": "web_search_result", "url": "https://meteo.example", "title": "Météo Lyon",
                                  "encrypted_content": "ZW5j", "page_age": None}]}
    claude_server.responses = [
        (200, sse([{"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "json": '{"query": "météo Lyon"}'},
                   search_result], "pause_turn")),
        (200, sse([{"type": "text", "text": "Demain à Lyon : 14 °C et du soleil."}], "end_turn")),
    ]
    agent = make_cloud_agent(config, claude_server, runner)
    rec = Recorder()
    assert agent.ask("quelle météo demain à Lyon ?", rec.emit, rec.confirm) == "Demain à Lyon : 14 °C et du soleil."
    assert "web_search" in rec.types()
    second = claude_server.requests[1]["body"]
    # La reprise renvoie le tour en pause tel quel, sans message « Continue » ajouté
    assert second["messages"][-1]["role"] == "assistant"
    assert second["messages"][-1]["content"][0]["type"] == "server_tool_use"


def test_claude_refusal_and_errors(config, claude_server):
    runner = FakeRunner()
    claude_server.responses = [(200, sse([], "refusal"))]
    agent = make_cloud_agent(config, claude_server, runner)
    rec = Recorder()
    agent.ask("demande refusée", rec.emit, rec.confirm)
    assert any(e["type"] == "notice" and "décliné" in e["text"] for e in rec.events)

    claude_server.responses = [(401, json.dumps({"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}))]
    rec = Recorder()
    agent.ask("encore", rec.emit, rec.confirm)
    errors = [e["message"] for e in rec.events if e["type"] == "error"]
    assert errors and "Clé API Claude invalide" in errors[0]
    # L'historique reste valide (chaque demande se termine par une réponse)
    assert agent.conversation.items[-1]["kind"] == "assistant"


def test_claude_sensitive_tool_denied(config, claude_server):
    runner = FakeRunner()
    claude_server.responses = [
        (200, sse([{"type": "tool_use", "id": "toolu_9", "name": "run_command",
                    "json": '{"command": "rm -r ~/Téléchargements/vieux", "reason": "faire de la place"}'}], "tool_use")),
        (200, sse([{"type": "text", "text": "D'accord, je ne supprime rien."}], "end_turn")),
    ]
    agent = make_cloud_agent(config, claude_server, runner)
    rec = Recorder(approve=False)
    agent.ask("fais de la place", rec.emit, rec.confirm)
    assert rec.confirmations and "⚠" in rec.confirmations[0]["summary"]
    assert not any(call[0] == "bash" for call in runner.calls)  # rien n'a été exécuté
    result = claude_server.requests[1]["body"]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "refusé" in result["content"]


def test_claude_invalid_tool_input_is_reported_not_run(config, claude_server):
    runner = FakeRunner()
    claude_server.responses = [
        (200, sse([{"type": "tool_use", "id": "toolu_5", "name": "volume", "json": '{"action": "boom"}'}], "tool_use")),
        (200, sse([{"type": "text", "text": "Oups."}], "end_turn")),
    ]
    agent = make_cloud_agent(config, claude_server, runner)
    agent.ask("son", Recorder().emit, Recorder().confirm)
    assert not any(c[0] == "wpctl" for c in runner.calls)
    result = claude_server.requests[1]["body"]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Arguments invalides" in result["content"]


# --- Ollama --------------------------------------------------------------------------
def ollama_handler(server, handler, method, body):
    if method == "GET" and handler.path == "/api/tags":
        data = json.dumps({"models": [{"name": "qwen3:4b"}]}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return
    lines = server.responses.pop(0)
    data = "".join(json.dumps(line) + "\n" for line in lines).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


@pytest.fixture
def ollama_server():
    server = ScriptedServer(ollama_handler)
    yield server
    server.close()


class NoCloud:
    name, model = "cloud", "claude-opus-5-5"

    def available(self):
        return False, "pas de clé"


def test_ollama_tool_loop(config, ollama_server, monkeypatch, tmp_path):
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "steam.desktop").write_text("[Desktop Entry]\nType=Application\nName=Steam\nExec=steam %U\n", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "share"))
    config["local"]["url"] = ollama_server.url
    ollama_server.responses = [
        [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "launch_app", "arguments": {"name": "steam"}}}]}, "done": False},
         {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop",
          "prompt_eval_count": 900, "eval_count": 12}],
        [{"message": {"role": "assistant", "content": "Steam "}, "done": False},
         {"message": {"role": "assistant", "content": "démarre !"}, "done": False},
         {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}],
    ]
    runner = FakeRunner()
    agent = Agent(config, runner=runner, backends={"local": OllamaBackend(config), "cloud": NoCloud()})
    rec = Recorder()
    assert agent.ask("lance steam", rec.emit, rec.confirm) == "Steam démarre !"
    assert runner.spawned == [["gtk-launch", "steam"]]
    first, second = (r["body"] for r in ollama_server.requests)
    assert first["model"] == "qwen3:4b" and first["think"] is False and first["stream"] is True
    assert first["options"]["num_ctx"] == 8192
    assert {t["function"]["name"] for t in first["tools"]} >= {"launch_app", "volume"}
    assert "take_screenshot" not in {t["function"]["name"] for t in first["tools"]}
    assert second["messages"][-1] == {"role": "tool", "content": "Steam est lancé.", "tool_name": "launch_app"}


def test_ollama_unavailable_falls_back_cleanly(config):
    config["local"]["url"] = "http://127.0.0.1:9"  # personne n'écoute ici
    backend = OllamaBackend(config)
    ok, why = backend.available()
    assert not ok and "Ollama" in why
    agent = Agent(config, runner=FakeRunner(), backends={"local": backend, "cloud": NoCloud()})
    rec = Recorder()
    agent.ask("bonjour", rec.emit, rec.confirm)
    assert rec.events[0]["type"] == "error" and "Ollama" in rec.events[0]["message"]


def test_cancel_during_generation(config, claude_server):
    runner = FakeRunner()
    claude_server.responses = [(200, sse([{"type": "text", "text": "Une très longue réponse " * 20}], "end_turn"))]
    agent = make_cloud_agent(config, claude_server, runner)
    cancel = threading.Event()
    rec = Recorder()

    def emit(event):
        rec.emit(event)
        if event["type"] == "text":
            cancel.set()

    agent.ask("raconte", emit, rec.confirm, cancel=cancel)
    assert any(e["type"] == "notice" and "interrompue" in e["text"] for e in rec.events)
    assert agent.conversation.items[-1]["text"] == "(réponse interrompue)"
