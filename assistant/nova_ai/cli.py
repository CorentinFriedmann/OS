"""Commande `nova` : discuter avec Nova dans le terminal et la configurer.

  nova                      discussion interactive
  nova "question"           question rapide
  nova setup                assistant de configuration (IA locale, clé Claude, mode)
  nova mode auto|local|cloud
  nova privacy on|off       confidentialité stricte (jamais de cloud)
  nova model [nom]          modèle local (téléchargé si besoin)
  nova status [--waybar]    état (JSON pour l'orbe de la barre)
  nova reset                nouvelle conversation
  nova daemon               démarre le démon (utilisé par systemd)
"""
from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys

from . import __version__
from .config import (get_api_key, load_config, recommended_local_model, save_api_key, save_config,
                     total_memory_gb)
from .client import DaemonUnavailable, NovaClient

ORB = "\U000F0674"  # icône « étincelles » (Nerd Font)
C = {
    "cyan": "\033[38;2;0;240;255m", "magenta": "\033[38;2;255;43;214m", "violet": "\033[38;2;138;92;255m",
    "green": "\033[38;2;61;255;168m", "red": "\033[38;2;255;56;96m", "yellow": "\033[38;2;255;210;63m",
    "dim": "\033[2m", "bold": "\033[1m", "reset": "\033[0m",
}
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    C = {key: "" for key in C}


def paint(color: str, text: str) -> str:
    return f"{C[color]}{text}{C['reset']}"


# --- affichage d'une réponse en flux --------------------------------------------------
class Printer:
    def __init__(self):
        self.thinking_shown = False

    def event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "turn_start":
            badge = "🔒 local" if event["backend"] == "local" else "☁  cloud"
            print(paint("dim", f"{badge} · {event['model']}"))
            print(paint("cyan", f"{ORB} Nova ") , end="", flush=True)
        elif kind == "text":
            print(event["text"], end="", flush=True)
        elif kind == "thinking" and not self.thinking_shown:
            self.thinking_shown = True
            print(paint("dim", "(réflexion…) "), end="", flush=True)
        elif kind == "web_search":
            print(paint("violet", "\n  🌐 recherche sur le web…"), flush=True)
        elif kind == "tool_start":
            print(paint("violet", f"\n  ⚙ {event['label']}…"), end="", flush=True)
        elif kind == "tool_end":
            mark = paint("green", " ✓") if event.get("ok") else paint("red", " ✗ refusé" if event.get("denied") else " ✗")
            print(mark, flush=True)
        elif kind == "progress":
            print(paint("dim", f"\n  {event['text']}"), flush=True)
        elif kind == "notice":
            print(paint("yellow", f"\n  {event['text']}"), flush=True)
        elif kind == "error":
            print(paint("red", f"\n  ✗ {event['message']}"), flush=True)
        elif kind == "turn_end":
            print()

    @staticmethod
    def confirm(request: dict) -> bool:
        color = "red" if request.get("risk") == "sensitive" else "yellow"
        print("\n" + paint(color, "┌─ Confirmation requise"))
        for line in request.get("summary", "").splitlines():
            print(paint(color, "│ ") + line)
        print(paint(color, "└─"), end="")
        try:
            answer = input(" Autoriser ? [o/N] ").strip().lower()
        except EOFError:
            return False
        return answer in ("o", "oui", "y", "yes")


def ask_once(client: NovaClient, text: str) -> None:
    printer = Printer()
    client.ask(text, printer.event, printer.confirm)


def chat(client: NovaClient) -> None:
    try:
        import readline  # noqa: F401 - historique et édition de la ligne
    except ImportError:
        pass
    print(paint("cyan", f"{ORB} Nova IA {__version__}") + paint("dim", " — /reset nouvelle conversation, /local ou /cloud en préfixe, Ctrl+D pour quitter"))
    while True:
        try:
            text = input(paint("magenta", "\n❯ "))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text.strip():
            continue
        if text.strip() == "/reset":
            client.request("reset")
            print(paint("dim", "Nouvelle conversation."))
            continue
        try:
            ask_once(client, text)
        except KeyboardInterrupt:
            client.request("cancel")
            print(paint("dim", "\n(interrompu)"))


# --- état pour Waybar ---------------------------------------------------------------------
def waybar_status() -> dict:
    try:
        status = NovaClient(autostart=False).request("status")
    except (DaemonUnavailable, OSError, json.JSONDecodeError):
        return {"text": ORB, "class": "offline", "tooltip": "Nova IA est arrêtée\nClic : démarrer et ouvrir l'assistant"}
    local, cloud = status.get("local", {}), status.get("cloud", {})
    lines = ["Nova IA — " + ("réfléchit…" if status.get("state") == "thinking" else "prête"),
             f"🔒 Local : {local.get('model', '?')}" + ("" if local.get("ok") else " (indisponible)"),
             f"☁  Cloud : {cloud.get('model', '?')}" + ("" if cloud.get("ok") else " (non configuré)"),
             f"Mode : {status.get('mode', 'auto')}" + (" · confidentialité stricte" if status.get("privacy_strict") else ""),
             "Clic : parler à Nova · Clic droit : réglages"]
    classes = []
    if status.get("state") == "thinking":
        classes.append("thinking")
    if not local.get("ok") and not cloud.get("ok"):
        classes.append("offline")
    elif status.get("mode") == "cloud" or (status.get("state") == "thinking" and status.get("last_backend") == "cloud"):
        classes.append("cloud")
    else:
        classes.append("local")
    return {"text": ORB, "class": classes, "tooltip": "\n".join(lines)}


# --- configuration ----------------------------------------------------------------------------
def _reload_daemon() -> None:
    try:
        NovaClient(autostart=False).request("reload")
    except (DaemonUnavailable, OSError):
        pass


def _yes(question: str, default: bool = True) -> bool:
    hint = "[O/n]" if default else "[o/N]"
    answer = input(f"{question} {hint} ").strip().lower()
    return default if not answer else answer in ("o", "oui", "y", "yes")


def pull_model(config: dict, model: str) -> bool:
    from .backends.ollama import OllamaBackend
    from .backends import BackendError

    backend = OllamaBackend(config)
    last = [""]

    def progress(status: str, ratio: float) -> None:
        if ratio >= 0:
            bar = "█" * int(ratio * 30)
            print(f"\r  {paint('cyan', bar.ljust(30, '░'))} {ratio * 100:5.1f} %  {status[:30]:<30}", end="", flush=True)
        elif status != last[0]:
            print(f"\r  {status:<70}", end="", flush=True)
        last[0] = status

    try:
        backend.pull(model, progress)
        print("\n  " + paint("green", f"✓ {model} est prêt."))
        return True
    except BackendError as error:
        print("\n  " + paint("red", f"✗ {error}"))
        return False


def setup() -> None:
    config = load_config()
    print(paint("cyan", f"\n  {ORB}  Configuration de Nova IA\n"))

    # 1. IA locale
    print(paint("bold", "1. IA locale (privée, hors ligne, gratuite)"))
    if shutil.which("systemctl") and subprocess.run(["systemctl", "is-active", "--quiet", "ollama"]).returncode != 0:
        print(paint("yellow", "  Ollama n'est pas démarré. Lance : sudo systemctl enable --now ollama"))
    memory = total_memory_gb()
    suggestion = recommended_local_model(memory)
    print(f"  Mémoire vive détectée : {memory:.0f} Go → modèle conseillé : {paint('cyan', suggestion)}")
    model = input(f"  Modèle local [{suggestion}] : ").strip() or suggestion
    config["local"]["model"] = model
    if _yes(f"  Télécharger {model} maintenant ?"):
        pull_model(config, model)

    # 2. Claude
    print(paint("bold", "\n2. Claude (cloud) : le plus intelligent, avec recherche web"))
    print(paint("dim", "  Nécessite une clé API Anthropic (console.anthropic.com), facturée à l'usage.\n"
                       "  Nova n'utilise le cloud que pour les demandes qui en ont besoin."))
    if get_api_key():
        print(paint("green", "  ✓ Une clé API est déjà configurée."))
        replace = _yes("  La remplacer ?", default=False)
    else:
        replace = _yes("  Configurer une clé maintenant ?")
    if replace:
        key = getpass.getpass("  Clé API (saisie masquée) : ").strip()
        if key:
            path = save_api_key(key)
            print(paint("green", f"  ✓ Clé enregistrée dans {path} (lisible par toi seul)."))
            try:
                import anthropic

                anthropic.Anthropic(api_key=key).models.list(limit=1)
                print(paint("green", "  ✓ Connexion à Claude réussie."))
            except Exception as error:  # noqa: BLE001
                print(paint("yellow", f"  ! Vérification impossible : {error}"))

    # 3. Mode
    print(paint("bold", "\n3. Mode de fonctionnement"))
    print("  auto  : local par défaut, Claude pour le web, l'analyse d'écran et les tâches complexes (conseillé)")
    print("  local : toujours en local          cloud : toujours Claude")
    mode = input(f"  Mode [{config['mode']}] : ").strip().lower() or config["mode"]
    if mode in ("auto", "local", "cloud"):
        config["mode"] = mode
    path = save_config(config)
    _reload_daemon()
    print(paint("green", f"\n  ✓ Configuration enregistrée ({path}). Super+Espace pour parler à Nova !\n"))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    if command in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if command in ("-V", "--version"):
        print(f"Nova IA {__version__}")
        return 0
    if command == "daemon":
        from .daemon import main as daemon_main

        daemon_main()
        return 0
    if command == "status":
        status = waybar_status()
        print(json.dumps(status, ensure_ascii=False) if "--waybar" in args else status["tooltip"])
        return 0
    if command == "setup":
        setup()
        return 0
    if command in ("mode", "privacy", "model"):
        config = load_config()
        value = args[1] if len(args) > 1 else ""
        if command == "mode":
            if value not in ("auto", "local", "cloud"):
                print(f"Mode actuel : {config['mode']} (choix : auto, local, cloud)")
                return 0 if not value else 2
            config["mode"] = value
        elif command == "privacy":
            if value not in ("on", "off"):
                print(f"Confidentialité stricte : {'activée' if config['privacy']['strict_local'] else 'désactivée'}")
                return 0 if not value else 2
            config["privacy"]["strict_local"] = value == "on"
        else:
            if not value:
                print(f"Modèle local : {config['local']['model']}")
                return 0
            config["local"]["model"] = value
            if not pull_model(config, value):
                return 1
        save_config(config)
        _reload_daemon()
        print(paint("green", "✓ Réglage enregistré."))
        return 0
    client = NovaClient()
    try:
        if command == "reset":
            client.request("reset")
            print("Nouvelle conversation.")
        elif args:
            ask_once(client, " ".join(args))
        else:
            chat(client)
    except DaemonUnavailable as error:
        print(paint("red", f"✗ {error}\n  Démarre-le avec : systemctl --user start nova-daemon"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
