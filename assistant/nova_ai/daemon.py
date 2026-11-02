"""Démon de Nova IA : garde la conversation et sert l'overlay, la CLI et Waybar.

Protocole : une connexion Unix ($XDG_RUNTIME_DIR/nova/assistant.sock), des
messages JSON d'une ligne.
  → {"op": "ask", "text": "...", "mode": "auto|local|cloud"}   réponses en flux, puis {"type": "done"}
  → {"op": "confirm_reply", "id": "...", "approved": true}
  → {"op": "cancel"} | {"op": "reset"} | {"op": "status"} | {"op": "history"} | {"op": "reload"} | {"op": "ping"}
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import threading
from pathlib import Path

from .agent import Agent
from .config import load_config, socket_path

CONFIRM_TIMEOUT_S = 120


class Connection:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.closed = False

    def send(self, message: dict) -> None:
        if self.closed:
            return
        try:
            self.writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
        except (ConnectionError, RuntimeError):
            self.closed = True


class _Waiter:
    def __init__(self):
        self.event = threading.Event()
        self.approved = False

    def resolve(self, approved: bool) -> None:
        self.approved = approved
        self.event.set()


class NovaDaemon:
    def __init__(self, agent: Agent, path: Path | None = None, notify_waybar: bool = True):
        self.agent = agent
        self.path = Path(path or socket_path())
        self.notify_waybar = notify_waybar
        self.busy = False
        self.cancel = threading.Event()
        self.pending: dict[str, tuple[_Waiter, Connection]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.server: asyncio.base_events.Server | None = None

    # --- cycle de vie -------------------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            self.path.unlink()
        self.server = await asyncio.start_unix_server(self._serve_client, path=str(self.path))
        os.chmod(self.path, 0o600)

    async def serve_forever(self) -> None:
        await self.start()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass
        async with self.server:
            await stop.wait()
        self.path.unlink(missing_ok=True)

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.path.unlink(missing_ok=True)

    # --- clients ------------------------------------------------------------------------
    async def _serve_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = Connection(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    conn.send({"type": "error", "message": "message JSON invalide"})
                    continue
                await self._dispatch(message, conn)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            conn.closed = True
            for key, (waiter, owner) in list(self.pending.items()):
                if owner is conn:  # l'overlay s'est fermé pendant une confirmation : refus
                    self.pending.pop(key, None)
                    waiter.resolve(False)
            writer.close()

    def status(self) -> dict:
        availability = self.agent.availability()
        return {
            "type": "status",
            "state": "thinking" if self.busy else "idle",
            "mode": self.agent.config.get("mode", "auto"),
            "last_backend": self.agent.conversation.last_backend(),
            "local": availability.get("local", {}),
            "cloud": availability.get("cloud", {}),
            "privacy_strict": self.agent.config.get("privacy", {}).get("strict_local", False),
        }

    async def _dispatch(self, message: dict, conn: Connection) -> None:
        op = message.get("op")
        if op == "ping":
            conn.send({"type": "pong"})
        elif op == "status":
            conn.send(await asyncio.to_thread(self.status))
        elif op == "history":
            conn.send({"type": "history", "items": self.agent.conversation.transcript()})
        elif op == "reset":
            if not self.busy:
                self.agent.reset()
            conn.send({"type": "ok"})
        elif op == "cancel":
            self.cancel.set()
            for key, (waiter, _owner) in list(self.pending.items()):
                self.pending.pop(key, None)
                waiter.resolve(False)
            conn.send({"type": "ok"})
        elif op == "reload":
            self.agent.config = load_config()
            conn.send({"type": "ok"})
        elif op == "confirm_reply":
            entry = self.pending.pop(str(message.get("id")), None)
            if entry:
                entry[0].resolve(bool(message.get("approved")))
        elif op == "ask":
            text = str(message.get("text", "")).strip()
            if not text:
                conn.send({"type": "error", "message": "Demande vide."})
                conn.send({"type": "done"})
            elif self.busy:
                conn.send({"type": "error", "message": "Nova répond déjà à une autre demande."})
                conn.send({"type": "done"})
            else:
                self.busy = True
                self.cancel.clear()
                self._signal_waybar()
                self.loop.run_in_executor(None, self._run_turn, text, message.get("mode"), conn)
        else:
            conn.send({"type": "error", "message": f"opération inconnue : {op}"})

    # --- tour de conversation (thread de travail) ------------------------------------------
    def _emit_from_thread(self, conn: Connection, event: dict) -> None:
        self.loop.call_soon_threadsafe(conn.send, event)

    def _confirm_from_thread(self, conn: Connection, request: dict) -> bool:
        if conn.closed:
            return False
        waiter = _Waiter()
        self.pending[str(request["id"])] = (waiter, conn)
        self._emit_from_thread(conn, request)
        if not waiter.event.wait(CONFIRM_TIMEOUT_S):
            self.pending.pop(str(request["id"]), None)
            return False
        return waiter.approved

    def _run_turn(self, text: str, mode: str | None, conn: Connection) -> None:
        try:
            self.agent.ask(
                text,
                emit=lambda event: self._emit_from_thread(conn, event),
                confirm=lambda request: self._confirm_from_thread(conn, request),
                cancel=self.cancel,
                mode=mode if mode in ("auto", "local", "cloud") else None,
            )
        except Exception as error:  # noqa: BLE001 - le démon doit survivre à tout
            self._emit_from_thread(conn, {"type": "error", "message": f"Erreur inattendue : {error}"})
        finally:
            self.busy = False
            self._emit_from_thread(conn, {"type": "done"})
            self._signal_waybar()

    def _signal_waybar(self) -> None:
        """Rafraîchit immédiatement l'orbe IA de la barre (signal RTMIN+8)."""
        if self.notify_waybar:
            self.agent.runner.run(["pkill", "-RTMIN+8", "-x", "waybar"], timeout=2)


def main() -> None:
    agent = Agent(load_config())
    daemon = NovaDaemon(agent)
    asyncio.run(daemon.serve_forever())


if __name__ == "__main__":
    main()
