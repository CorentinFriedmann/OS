"""Client du démon Nova (utilisé par la CLI, l'overlay et Waybar)."""
from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable

from .config import socket_path


class DaemonUnavailable(Exception):
    pass


class NovaClient:
    def __init__(self, path: Path | None = None, autostart: bool = True):
        self.path = Path(path or socket_path())
        self.autostart = autostart

    def _connect(self, timeout: float = 5.0) -> socket.socket:
        attempts = 15 if self.autostart else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(str(self.path))
                return sock
            except OSError as error:
                last_error = error
                if attempt == 0 and self.autostart:
                    subprocess.run(["systemctl", "--user", "start", "nova-daemon.service"],
                                   capture_output=True, check=False, timeout=10)
                if attempts > 1:
                    time.sleep(0.2)
        raise DaemonUnavailable(f"Le démon Nova IA ne répond pas ({last_error}).")

    @staticmethod
    def _lines(sock: socket.socket):
        buffer = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                return
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip():
                    yield json.loads(line)

    def request(self, op: str, **fields) -> dict:
        with self._connect() as sock:
            sock.sendall((json.dumps({"op": op, **fields}) + "\n").encode())
            for message in self._lines(sock):
                return message
        return {}

    def ask(self, text: str, on_event: Callable[[dict], None], on_confirm: Callable[[dict], bool],
            mode: str | None = None) -> None:
        """Envoie une demande et relaie les évènements jusqu'à la fin de la réponse."""
        with self._connect(timeout=900) as sock:
            payload = {"op": "ask", "text": text}
            if mode:
                payload["mode"] = mode
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            for event in self._lines(sock):
                if event.get("type") == "confirm":
                    approved = bool(on_confirm(event))
                    reply = {"op": "confirm_reply", "id": event["id"], "approved": approved}
                    sock.sendall((json.dumps(reply) + "\n").encode())
                    continue
                on_event(event)
                if event.get("type") == "done":
                    return
