"""Test du démon : protocole socket, flux d'évènements, confirmation aller-retour."""
from __future__ import annotations

import asyncio
import threading
import time

from nova_ai.agent import Agent
from nova_ai.backends import StepResult, ToolCall
from nova_ai.client import NovaClient
from nova_ai.daemon import NovaDaemon
from tests.conftest import FakeRunner


class ScriptedBackend:
    name, model = "local", "qwen3:4b"

    def __init__(self):
        self.steps = 0

    def available(self):
        return True, ""

    def step(self, conversation, tools, emit, cancel):
        self.steps += 1
        if self.steps == 1:
            emit({"type": "text", "text": "Je regarde."})
            return StepResult("Je regarde.", [ToolCall("c1", "run_command", {"command": "uptime", "reason": "état"})],
                              "tool_use")
        emit({"type": "text", "text": "Ton PC tourne depuis 3 h."})
        return StepResult("Ton PC tourne depuis 3 h.")


class Off:
    name, model = "cloud", "claude-opus-5-5"

    def available(self):
        return False, "non configuré"


def start_daemon(agent, path):
    loop = asyncio.new_event_loop()
    daemon = NovaDaemon(agent, path, notify_waybar=False)
    ready = threading.Event()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(daemon.start())
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    ready.wait(5)
    return daemon, loop, thread


def stop_daemon(daemon, loop, thread):
    """Arrêt propre : ferme le serveur, annule les connexions restantes, arrête puis ferme la boucle."""
    asyncio.run_coroutine_threadsafe(daemon.stop(), loop).result(5)

    async def cancel_pending():
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run_coroutine_threadsafe(cancel_pending(), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)
    loop.close()  # libère aussi les sockets internes de la boucle (sinon ResourceWarning)


def test_daemon_roundtrip_with_confirmation(config, tmp_path):
    runner = FakeRunner()
    agent = Agent(config, runner=runner, backends={"local": ScriptedBackend(), "cloud": Off()}, data_dir=tmp_path)
    path = tmp_path / "nova.sock"
    daemon, loop, thread = start_daemon(agent, path)
    try:
        client = NovaClient(path, autostart=False)
        assert client.request("ping") == {"type": "pong"}
        status = client.request("status")
        assert status["state"] == "idle" and status["local"]["ok"] is True and status["cloud"]["ok"] is False

        events, confirmations = [], []

        def on_confirm(request):
            confirmations.append(request)
            return True

        client.ask("depuis quand mon PC est allumé ?", events.append, on_confirm)
        kinds = [e["type"] for e in events]
        assert kinds[0] == "turn_start" and kinds[-1] == "done"
        assert confirmations and confirmations[0]["summary"].startswith("Exécuter")
        assert ["bash", "-lc", "uptime"] in runner.calls
        assert "".join(e["text"] for e in events if e["type"] == "text").endswith("depuis 3 h.")

        history = client.request("history")["items"]
        assert [h["role"] for h in history] == ["user", "assistant", "tool", "assistant"]
        assert client.request("reset") == {"type": "ok"}
        assert client.request("history")["items"] == []
    finally:
        stop_daemon(daemon, loop, thread)


def test_daemon_denies_when_client_disconnects(config, tmp_path):
    runner = FakeRunner()
    agent = Agent(config, runner=runner, backends={"local": ScriptedBackend(), "cloud": Off()}, data_dir=tmp_path)
    path = tmp_path / "nova2.sock"
    daemon, loop, thread = start_daemon(agent, path)
    try:
        import json
        import socket

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(path))
        sock.sendall(json.dumps({"op": "ask", "text": "uptime ?"}).encode() + b"\n")
        buffer = b""
        while b'"confirm"' not in buffer:
            buffer += sock.recv(4096)
        sock.close()  # l'overlay est fermé sans répondre
        for _ in range(50):
            if not daemon.busy:
                break
            time.sleep(0.1)
        assert not daemon.busy
        assert not any(call[0] == "bash" for call in runner.calls)  # refus par défaut
    finally:
        stop_daemon(daemon, loop, thread)
