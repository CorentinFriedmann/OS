"""La voix de Nova : tu parles, elle répond à voix haute. 100 % local.

- Reconnaissance vocale : faster-whisper (modèle « small » ou « base » selon la mémoire vive)
- Voix de Nova : Piper, voix française naturelle (fr_FR-siwis-medium)

Le moteur est installé une seule fois, au premier usage (bouton micro ou `nova voix installer`),
dans ~/.local/share/nova/voix/ : un environnement Python dédié (~500 Mo) + les modèles (~250 Mo).
Il tourne dans un processus à part (voice_worker.py), pour ne pas alourdir l'assistant.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from .config import data_dir, load_config, total_memory_gb

PIP_PACKAGES = ("faster-whisper>=1.1,<2", "piper-tts>=1.2,<2")
VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_VOICE = "fr_FR-siwis-medium"
WORKER = Path(__file__).with_name("voice_worker.py")
Progress = Callable[[str], None]


def voice_dir() -> Path:
    return data_dir() / "voix"


def env_python() -> Path:
    return voice_dir() / "env" / "bin" / "python"


def voice_settings() -> dict:
    settings = {"stt_model": "", "tts_voice": DEFAULT_VOICE, "speak_replies": "voice"}
    settings.update(load_config().get("voice", {}) or {})
    return settings


def stt_model(settings: dict | None = None) -> str:
    """Modèle de reconnaissance : « small » (meilleur) ou « base » (plus léger) selon la mémoire."""
    chosen = (settings or voice_settings()).get("stt_model")
    if chosen:
        return chosen
    return "base" if total_memory_gb() < 12 else "small"


def voice_files(name: str) -> tuple[Path, Path]:
    folder = voice_dir() / "voix-piper"
    return folder / f"{name}.onnx", folder / f"{name}.onnx.json"


def installed() -> bool:
    onnx, meta = voice_files(voice_settings()["tts_voice"])
    return env_python().exists() and onnx.exists() and meta.exists()


def available() -> tuple[bool, str]:
    """(prêt, raison) pour la dictée."""
    if not shutil.which("pw-record"):
        return False, "Micro indisponible : PipeWire (pw-record) est introuvable."
    if not installed():
        return False, "La voix de Nova n'est pas encore installée."
    return True, ""


def _voice_url(name: str, suffix: str) -> str:
    # fr_FR-siwis-medium → fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx
    lang_region, speaker, quality = name.split("-", 2)
    lang = lang_region.split("_")[0]
    return f"{VOICES_URL}/{lang}/{lang_region}/{speaker}/{quality}/{name}{suffix}"


def _download(url: str, target: Path, progress: Progress) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = last = 0
        while chunk := response.read(1 << 16):
            out.write(chunk)
            done += len(chunk)
            if total and done * 10 // total != last:
                last = done * 10 // total
                progress(f"{target.name} : {last * 10} %")
    partial.replace(target)


def install(progress: Progress = print, runner=subprocess.run) -> bool:
    """Installe le moteur vocal (une seule fois). Renvoie True si tout est prêt."""
    settings = voice_settings()
    try:
        if not env_python().exists():
            progress("Création de l'environnement vocal…")
            runner([sys.executable, "-m", "venv", str(voice_dir() / "env")], check=True)
        progress("Téléchargement du moteur vocal (faster-whisper, Piper : ~500 Mo)…")
        runner([str(env_python()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                "--upgrade", *PIP_PACKAGES], check=True)
        onnx, meta = voice_files(settings["tts_voice"])
        if not meta.exists():
            _download(_voice_url(settings["tts_voice"], ".onnx.json"), meta, progress)
        if not onnx.exists():
            progress("Téléchargement de la voix française de Nova (~60 Mo)…")
            _download(_voice_url(settings["tts_voice"], ".onnx"), onnx, progress)
        progress(f"Téléchargement du modèle de reconnaissance « {stt_model(settings)} »…")
        runner([str(env_python()), str(WORKER), "prepare", "--model", stt_model(settings),
                "--models-dir", str(voice_dir() / "modeles")], check=True)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        progress(f"✗ Installation de la voix impossible : {error}")
        return False
    progress("✓ La voix de Nova est prête.")
    return True


class Recorder:
    """Enregistre le micro (PipeWire, 16 kHz mono) jusqu'à stop()."""

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

    def stop(self) -> Path:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        return self.path

    def stop_and_transcribe(self) -> str:
        try:
            return transcribe(self.stop())
        finally:
            self.path.unlink(missing_ok=True)


def transcribe(wav: Path, runner=subprocess.run) -> str:
    """Texte prononcé dans le fichier (vide si rien n'a été compris)."""
    if not installed():
        return ""
    try:
        result = runner([str(env_python()), str(WORKER), "transcribe", str(wav), "--model", stt_model(),
                         "--models-dir", str(voice_dir() / "modeles")],
                        capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return " ".join(result.stdout.split()).strip()


def speech_text(text: str, limit: int = 700) -> str:
    """Texte d'une réponse adapté à la lecture à voix haute (sans code, liens ni mise en forme)."""
    text = re.sub(r"```.*?```", " (voir le code à l'écran) ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>|]+", " ", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = " ".join(text.split())
    if len(text) > limit:
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = (cut[: end + 1] if end > limit // 3 else cut) + " La suite est à l'écran."
    return text.strip()


_speaker: subprocess.Popen | None = None


def stop_speaking() -> None:
    global _speaker
    if _speaker and _speaker.poll() is None:
        _speaker.terminate()
    _speaker = None


def speak(text: str) -> None:
    """Lit le texte à voix haute en arrière-plan (Piper, sinon espeak-ng)."""
    global _speaker
    text = speech_text(text)
    if not text:
        return
    stop_speaking()
    onnx, _meta = voice_files(voice_settings()["tts_voice"])
    player = next((p for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)
    if installed() and player:
        script = (f'tmp=$(mktemp --suffix=.wav) && "$0" "$1" speak --voice "$2" --out "$tmp" '
                  f'&& {player} "$tmp"; rm -f "$tmp"')
        _speaker = subprocess.Popen(["sh", "-c", script, str(env_python()), str(WORKER), str(onnx)],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True, text=True)
        try:
            _speaker.stdin.write(text)
            _speaker.stdin.close()
        except OSError:
            pass
    elif shutil.which("espeak-ng"):
        _speaker = subprocess.Popen(["espeak-ng", "-v", "fr", "-s", "165", text],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
