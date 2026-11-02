from __future__ import annotations

import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova_ai.config import DEFAULTS  # noqa: E402
from nova_ai.runner import Completed, Runner  # noqa: E402


class FakeRunner(Runner):
    """Enregistre les commandes au lieu de les exécuter."""

    def __init__(self, responses: dict | None = None, available: tuple = ("gtk-launch", "fd", "ghostty")):
        self.calls: list[list[str]] = []
        self.spawned: list[list[str]] = []
        self.inputs: list[str | None] = []
        self.responses = responses or {}
        self.available = available

    def run(self, argv, timeout=15, input_text=None, env=None):
        self.calls.append(list(argv))
        self.inputs.append(input_text)
        for prefix, value in self.responses.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return value if isinstance(value, Completed) else Completed(0, value, "")
        return Completed(0, "", "")

    def spawn(self, argv):
        self.spawned.append(list(argv))
        return True

    def which(self, name):
        return f"/usr/bin/{name}" if name in self.available else None


@pytest.fixture
def config():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["local"]["model"] = "qwen3:4b"
    return cfg


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return home


class ScriptedServer:
    """Petit serveur HTTP local qui rejoue des réponses scriptées et garde les requêtes."""

    def __init__(self, handler_factory):
        self.requests: list[dict] = []
        self.responses: list = []
        server_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                return json.loads(raw) if raw else None

            def do_GET(self):
                handler_factory(server_self, self, "GET", None)

            def do_POST(self):
                body = self._body()
                server_self.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                handler_factory(server_self, self, "POST", body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
