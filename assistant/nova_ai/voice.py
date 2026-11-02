"""Dictée vocale de Nova (optionnelle) : PipeWire + whisper.cpp, 100 % local.

Installation : `paru -S whisper.cpp` puis un modèle, par exemple
  ~/.local/share/nova/whisper/ggml-base.bin
(https://huggingface.co/ggerganov/whisper.cpp, fichier ggml-base.bin).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import data_dir, load_config

WHISPER_BINARIES = ("whisper-cli", "whisper-cpp", "whisper.cpp")


def whisper_binary() -> str | None:
    return next((path for name in WHISPER_BINARIES if (path := shutil.which(name))), None)


def whisper_model() -> Path | None:
    configured = load_config().get("voice", {}).get("whisper_model")
    candidates = [Path(configured)] if configured else []
    candidates += sorted((data_dir() / "whisper").glob("ggml-*.bin"))
    return next((p for p in candidates if p.is_file()), None)


def available() -> tuple[bool, str]:
    if not shutil.which("pw-record"):
        return False, "Dictée indisponible : PipeWire (pw-record) est introuvable."
    if not whisper_binary():
        return False, "Dictée indisponible : installe whisper.cpp (paru -S whisper.cpp)."
    if not whisper_model():
        return False, f"Dictée indisponible : place un modèle ggml-*.bin dans {data_dir() / 'whisper'}."
    return True, ""


class Recorder:
    def __init__(self):
        fd, path = tempfile.mkstemp(prefix="nova-voix-", suffix=".wav")
        os.close(fd)
        self.path = Path(path)
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(
            ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", str(self.path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def stop_and_transcribe(self) -> str:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        try:
            binary, model = whisper_binary(), whisper_model()
            if not binary or not model:
                return ""
            result = subprocess.run(
                [binary, "-m", str(model), "-f", str(self.path), "-l", "fr", "-nt", "-np", "-t", str(os.cpu_count() or 4)],
                capture_output=True, text=True, timeout=120, check=False,
            )
            return " ".join(result.stdout.split()).strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""
        finally:
            self.path.unlink(missing_ok=True)


def speak(text: str) -> None:
    """Lecture à voix haute (piper si disponible, sinon espeak-ng)."""
    if shutil.which("espeak-ng"):
        subprocess.Popen(["espeak-ng", "-v", "fr", "-s", "165", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
