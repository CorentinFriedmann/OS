"""Exécution des commandes système (remplaçable dans les tests)."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Runner:
    """Lance des programmes sans passer par un shell (pas d'injection possible),
    sauf pour l'outil run_command qui le demande explicitement."""

    def run(self, argv: list[str], timeout: float = 15, input_text: str | None = None,
            env: dict | None = None) -> Completed:
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout, input=input_text,
                env={**os.environ, **(env or {})}, check=False,
            )
            return Completed(proc.returncode, proc.stdout, proc.stderr)
        except FileNotFoundError:
            return Completed(127, "", f"programme introuvable : {argv[0]}")
        except subprocess.TimeoutExpired:
            return Completed(124, "", f"délai dépassé ({int(timeout)} s)")

    def spawn(self, argv: list[str]) -> bool:
        """Démarre un programme graphique détaché de Nova (il survit au démon)."""
        try:
            subprocess.Popen(  # noqa: S603 - argv contrôlé, pas de shell
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
            return True
        except OSError:
            return False

    def which(self, name: str) -> str | None:
        return shutil.which(name)
