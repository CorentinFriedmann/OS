"""Configuration de Nova IA.

Fichiers :
  ~/.config/nova/assistant.toml   réglages (mode, modèles, confidentialité…)
  ~/.config/nova/secrets.env      clé API Claude (droits 600, jamais affichée)
"""
from __future__ import annotations

import copy
import os
import re
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CLOUD_MODEL = "claude-opus-5-5"

DEFAULTS: dict[str, Any] = {
    # auto : local par défaut, Claude quand c'est utile | local | cloud
    "mode": "auto",
    "local": {
        "url": "http://127.0.0.1:11434",
        "model": "",  # vide = choisi automatiquement selon la mémoire vive
        "num_ctx": 8192,
        "keep_alive": "30m",
    },
    "cloud": {
        "model": DEFAULT_CLOUD_MODEL,
        "effort": "medium",  # low | medium | high | xhigh | max
        "web_search": True,
        "max_tokens": 64000,
    },
    "privacy": {
        # true : Nova n'envoie jamais rien sur internet
        "strict_local": False,
        # demander avant d'envoyer un fichier, l'écran ou le presse-papiers au cloud
        "confirm_private_in_cloud": True,
    },
    "confirm": {
        "action": "never",  # actions courantes (ouvrir une appli, régler le son…)
        "sensitive": "always",  # commandes shell, installation de logiciels…
    },
    # stt_model : vide = « small » ou « base » selon la mémoire ; speak_replies : voice | always | never
    "voice": {"stt_model": "", "tts_voice": "fr_FR-siwis-medium", "speak_replies": "voice"},
    "conversation": {"idle_reset_minutes": 20, "max_exchanges": 40},
}


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "nova"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "nova"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/nova-{os.getuid()}"
    return Path(base) / "nova"


def socket_path() -> Path:
    return Path(os.environ.get("NOVA_SOCKET") or runtime_dir() / "assistant.sock")


def config_file() -> Path:
    return config_dir() / "assistant.toml"


def secrets_file() -> Path:
    return config_dir() / "secrets.env"


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict:
    path = path or config_file()
    user: dict = {}
    if path.exists():
        try:
            user = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            user = {}  # fichier abîmé : on repart des valeurs par défaut
    cfg = deep_merge(DEFAULTS, user)
    if cfg.get("mode") not in ("auto", "local", "cloud"):
        cfg["mode"] = "auto"
    if not cfg["local"].get("model"):
        cfg["local"]["model"] = recommended_local_model()
    return cfg


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def dumps_toml(cfg: dict) -> str:
    lines = ["# Nova IA — configuration (modifiable à la main ou avec « nova setup »)", ""]
    for key, value in cfg.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")
    for key, value in cfg.items():
        if isinstance(value, dict):
            lines += ["", f"[{key}]"]
            lines += [f"{k} = {_toml_value(v)}" for k, v in value.items() if not isinstance(v, dict)]
    return "\n".join(lines) + "\n"


def save_config(cfg: dict, path: Path | None = None) -> Path:
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_toml(cfg), encoding="utf-8")
    return path


def get_api_key() -> str | None:
    """Clé Claude : variable d'environnement, sinon ~/.config/nova/secrets.env."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        content = secrets_file().read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^\s*ANTHROPIC_API_KEY\s*=\s*['\"]?([^'\"\s]+)", content, re.M)
    return match.group(1) if match else None


def save_api_key(key: str) -> Path:
    path = secrets_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("# Clé API Claude de Nova IA — ne partage jamais ce fichier\n")
        handle.write(f"ANTHROPIC_API_KEY={key.strip()}\n")
    os.chmod(path, 0o600)
    return path


def total_memory_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 8.0


def recommended_local_model(memory_gb: float | None = None) -> str:
    """Modèle local adapté à la machine (Intel iGPU : inférence surtout CPU)."""
    memory_gb = total_memory_gb() if memory_gb is None else memory_gb
    if memory_gb < 12:
        return "qwen3:1.7b"
    if memory_gb < 24:
        return "qwen3:4b"
    return "qwen3:8b"
