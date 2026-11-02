"""Outils « bureau » : applications, fenêtres, son, luminosité, rappels, écran."""
from __future__ import annotations

import configparser
import difflib
import json
import os
import re
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..schema import obj
from . import Tool, ToolContext, ToolResult


def normalize(text: str) -> str:
    """Minuscules sans accents, pour comparer « Paramètres » et « parametres »."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


@dataclass
class DesktopApp:
    app_id: str
    name: str
    generic: str
    keywords: str
    exec_line: str


def application_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [data_home / "applications"] + [Path(d) / "applications" for d in data_dirs.split(":") if d]
    dirs += [Path("/var/lib/flatpak/exports/share/applications"),
             data_home / "flatpak/exports/share/applications"]
    return dirs


def _localized(section, key: str) -> str:
    for candidate in (f"{key}[fr_FR]", f"{key}[fr]", key):
        if candidate in section:
            return section[candidate]
    return ""


def list_applications(dirs: list[Path] | None = None) -> list[DesktopApp]:
    seen: dict[str, DesktopApp] = {}
    for directory in dirs or application_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.desktop")):
            app_id = path.relative_to(directory).as_posix().replace("/", "-")[: -len(".desktop")]
            if app_id in seen:
                continue  # le premier trouvé (utilisateur) masque les suivants
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str  # garder la casse des clés (Name[fr])
            try:
                parser.read(path, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError):
                continue
            if "Desktop Entry" not in parser:
                continue
            entry = parser["Desktop Entry"]
            if entry.get("Type", "Application") != "Application":
                continue
            if entry.get("NoDisplay", "false").lower() == "true" or entry.get("Hidden", "false").lower() == "true":
                continue
            seen[app_id] = DesktopApp(
                app_id=app_id,
                name=_localized(entry, "Name") or app_id,
                generic=_localized(entry, "GenericName"),
                keywords=_localized(entry, "Keywords"),
                exec_line=entry.get("Exec", ""),
            )
    return list(seen.values())


def find_application(query: str, apps: list[DesktopApp]) -> tuple[DesktopApp | None, list[DesktopApp]]:
    """Meilleure correspondance + quelques suggestions."""
    q = normalize(query)
    scored: list[tuple[float, DesktopApp]] = []
    for app in apps:
        name = normalize(app.name)
        haystack = " ".join(normalize(x) for x in (app.generic, app.keywords, app.app_id))
        if q == name or q == normalize(app.app_id):
            score = 1.0
        elif name.startswith(q):
            score = 0.92
        elif q in name:
            score = 0.85
        elif q in haystack:
            score = 0.75
        else:
            score = difflib.SequenceMatcher(None, q, name).ratio() * 0.8
        scored.append((score, app))
    scored.sort(key=lambda item: (-item[0], len(item[1].name)))
    best = scored[0] if scored else None
    suggestions = [app for score, app in scored[:5] if score > 0.35]
    if best and best[0] >= 0.6:
        return best[1], suggestions
    return None, suggestions


def launch_app(args: dict, ctx: ToolContext) -> ToolResult:
    apps = list_applications()
    app, suggestions = find_application(args["name"], apps)
    if app is None:
        hint = ", ".join(s.name for s in suggestions[:4])
        return ToolResult(False, f"Aucune application « {args['name']} » trouvée."
                          + (f" Suggestions : {hint}." if hint else ""))
    if ctx.runner.which("gtk-launch") and ctx.runner.spawn(["gtk-launch", app.app_id]):
        return ToolResult(True, f"{app.name} est lancé.")
    command = [part for part in app.exec_line.split() if not re.fullmatch(r"%[a-zA-Z]", part)]
    if command and ctx.runner.spawn(command):
        return ToolResult(True, f"{app.name} est lancé.")
    return ToolResult(False, f"Impossible de lancer {app.name}.")


def open_target(args: dict, ctx: ToolContext) -> ToolResult:
    target = args["target"].strip()
    if re.match(r"^(https?|mailto):", target, re.I):
        pass
    elif re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", target, re.I) and not target.startswith(("/", "~")):
        target = "https://" + target  # « wikipedia.org » -> https://wikipedia.org
    else:
        path = Path(os.path.expanduser(target))
        if not path.exists():
            return ToolResult(False, f"Le chemin {target} n'existe pas.")
        target = str(path)
    if ctx.runner.spawn(["xdg-open", target]):
        return ToolResult(True, f"Ouverture de {target}.")
    return ToolResult(False, "xdg-open est introuvable.")


def _hyprctl_json(ctx: ToolContext, what: str):
    result = ctx.runner.run(["hyprctl", "-j", what], timeout=3)
    if not result.ok:
        return None
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return None


def list_windows(args: dict, ctx: ToolContext) -> ToolResult:
    clients = _hyprctl_json(ctx, "clients")
    if clients is None:
        return ToolResult(False, "Hyprland ne répond pas (es-tu dans la session graphique ?).")
    lines = [
        f"- {c.get('class', '?')} : « {c.get('title', '')[:70]} » (bureau {c.get('workspace', {}).get('name', '?')})"
        for c in clients if c.get("mapped", True)
    ]
    return ToolResult(True, "\n".join(lines) or "Aucune fenêtre ouverte.")


def _lua_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # chaîne Lua valide (guillemets échappés)


def window_action(args: dict, ctx: ToolContext) -> ToolResult:
    action = args["action"]
    target = (args.get("target") or "").strip()
    selector = None
    if target:
        clients = _hyprctl_json(ctx, "clients") or []
        q = normalize(target)
        match = next((c for c in clients if q in normalize(c.get("class", ""))), None) or \
            next((c for c in clients if q in normalize(c.get("title", ""))), None)
        if match is None:
            return ToolResult(False, f"Aucune fenêtre ne correspond à « {target} ».")
        selector = f"address:{match.get('address')}"
    win = f", window = {_lua_string(selector)}" if selector else ""
    workspace = args.get("workspace")
    if action in ("move_to_workspace", "switch_workspace") and not isinstance(workspace, int):
        return ToolResult(False, "Il faut préciser le numéro du bureau.")
    if workspace is not None and not 1 <= workspace <= 10:
        return ToolResult(False, "Les bureaux vont de 1 à 10.")
    expressions = {
        "focus": f"hl.dsp.focus({{ window = {_lua_string(selector or '')} }})" if selector else None,
        "close": f"hl.dsp.window.close({{{win.lstrip(', ')}}})" if selector else "hl.dsp.window.close()",
        "fullscreen": f'hl.dsp.window.fullscreen({{ mode = "fullscreen", action = "toggle"{win} }})',
        "float": f'hl.dsp.window.float({{ action = "toggle"{win} }})',
        "move_to_workspace": f"hl.dsp.window.move({{ workspace = {workspace}{win} }})",
        "switch_workspace": f"hl.dsp.focus({{ workspace = {workspace} }})",
    }
    expression = expressions.get(action)
    if expression is None:
        return ToolResult(False, "Précise la fenêtre à activer.")
    result = ctx.runner.run(["hyprctl", "dispatch", expression], timeout=3)
    if not result.ok or "error" in result.stdout.lower():
        return ToolResult(False, f"Hyprland a refusé l'action : {(result.stdout or result.stderr).strip()}")
    return ToolResult(True, "C'est fait.")


def volume(args: dict, ctx: ToolContext) -> ToolResult:
    action, percent = args["action"], args.get("percent")
    sink = "@DEFAULT_AUDIO_SINK@"
    if action in ("set", "up", "down") and not isinstance(percent, int):
        percent = 10 if action != "set" else None
    if percent is not None and not 0 <= percent <= 150:
        return ToolResult(False, "Le volume doit être entre 0 et 150 %.")
    argv = {
        "set": ["wpctl", "set-volume", "-l", "1.5", sink, f"{percent}%"] if percent is not None else None,
        "up": ["wpctl", "set-volume", "-l", "1.5", sink, f"{percent}%+"],
        "down": ["wpctl", "set-volume", sink, f"{percent}%-"],
        "mute": ["wpctl", "set-mute", sink, "1"],
        "unmute": ["wpctl", "set-mute", sink, "0"],
    }.get(action)
    if argv is None:
        return ToolResult(False, "Précise le niveau de volume voulu.")
    result = ctx.runner.run(argv, timeout=3)
    if not result.ok:
        return ToolResult(False, f"Réglage du son impossible : {result.stderr.strip()}")
    now = ctx.runner.run(["wpctl", "get-volume", sink], timeout=3).stdout.strip()
    return ToolResult(True, f"Son réglé. État actuel : {now or 'inconnu'}.")


def brightness(args: dict, ctx: ToolContext) -> ToolResult:
    action, percent = args["action"], args.get("percent", 10)
    if not isinstance(percent, int) or not 1 <= percent <= 100:
        return ToolResult(False, "La luminosité doit être entre 1 et 100 %.")
    value = {"set": f"{percent}%", "up": f"{percent}%+", "down": f"{percent}%-"}[action]
    result = ctx.runner.run(["brightnessctl", "-e4", "-n2", "set", value], timeout=3)
    if not result.ok:
        return ToolResult(False, f"Réglage de la luminosité impossible : {result.stderr.strip()}")
    return ToolResult(True, "Luminosité réglée.")


def media_control(args: dict, ctx: ToolContext) -> ToolResult:
    action = args["action"]
    if action == "status":
        result = ctx.runner.run(["playerctl", "metadata", "--format",
                                 "{{artist}} — {{title}} ({{status}})"], timeout=3)
        return ToolResult(result.ok, result.stdout.strip() or "Aucun lecteur multimédia actif.")
    verb = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}[action]
    result = ctx.runner.run(["playerctl", verb], timeout=3)
    return ToolResult(result.ok, "C'est fait." if result.ok else "Aucun lecteur multimédia actif.")


def notify(args: dict, ctx: ToolContext) -> ToolResult:
    result = ctx.runner.run(["notify-send", "-a", "Nova", "-i", "nova", args["title"], args.get("body", "")], timeout=5)
    return ToolResult(result.ok, "Notification affichée." if result.ok else "Impossible d'afficher la notification.")


def set_reminder(args: dict, ctx: ToolContext) -> ToolResult:
    minutes, text = args["minutes"], args["text"].strip()
    if not 1 <= minutes <= 7 * 24 * 60:
        return ToolResult(False, "Un rappel doit être programmé entre 1 minute et 7 jours.")
    unit = f"nova-rappel-{int(time.time())}"
    result = ctx.runner.run([
        "systemd-run", "--user", f"--on-active={minutes}m", f"--unit={unit}",
        "--timer-property=AccuracySec=1s", "--description=Rappel Nova",
        "notify-send", "-a", "Nova", "-u", "critical", "-i", "nova", "Rappel", text,
    ], timeout=10)
    if not result.ok:
        return ToolResult(False, f"Impossible de programmer le rappel : {result.stderr.strip()}")
    at = time.strftime("%H:%M", time.localtime(time.time() + minutes * 60))
    return ToolResult(True, f"Rappel programmé à {at} : « {text} ».")


def take_screenshot(args: dict, ctx: ToolContext) -> ToolResult:
    monitors = _hyprctl_json(ctx, "monitors") or []
    width = max((m.get("width", 1920) for m in monitors), default=1920)
    scale = min(1.0, 1568 / max(1, width))  # limite la taille envoyée au modèle
    fd, path = tempfile.mkstemp(prefix="nova-ecran-", suffix=".jpg")
    os.close(fd)
    try:
        result = ctx.runner.run(["grim", "-s", f"{scale:.3f}", "-t", "jpeg", "-q", "85", path], timeout=10)
        data = Path(path).read_bytes() if result.ok else b""
    finally:
        Path(path).unlink(missing_ok=True)
    if not data:
        return ToolResult(False, "La capture d'écran a échoué.")
    return ToolResult(True, "Voici la capture de l'écran actuel.", image=data, image_type="image/jpeg")


def clipboard_read(args: dict, ctx: ToolContext) -> ToolResult:
    result = ctx.runner.run(["wl-paste", "--no-newline", "--type", "text"], timeout=3)
    if not result.ok:
        return ToolResult(False, "Le presse-papiers est vide ou ne contient pas de texte.")
    text = result.stdout
    if len(text) > 8000:
        text = text[:8000] + "\n[… tronqué]"
    return ToolResult(True, text)


def clipboard_write(args: dict, ctx: ToolContext) -> ToolResult:
    result = ctx.runner.run(["wl-copy"], timeout=3, input_text=args["text"])
    return ToolResult(result.ok, "Copié dans le presse-papiers." if result.ok else "Copie impossible.")


def network_status(args: dict, ctx: ToolContext) -> ToolResult:
    radios = ctx.runner.run(["nmcli", "-t", "-f", "WIFI,WWAN", "radio"], timeout=3).stdout.strip()
    active = ctx.runner.run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"], timeout=3)
    connections = [line.split(":") for line in active.stdout.splitlines() if line and ":lo" not in line]
    text = "Connexions actives : " + (", ".join(f"{c[0]} ({c[1]})" for c in connections if len(c) >= 2) or "aucune")
    if radios:
        text += f"\nWi-Fi : {'activé' if radios.split(':')[0] == 'enabled' else 'désactivé'}"
    return ToolResult(True, text)


TOOLS = [
    Tool("launch_app",
         "Open an installed application by name (e.g. 'firefox', 'fichiers', 'steam', 'calculatrice'). "
         "Call this whenever the user asks to open, launch or start a program.",
         obj({"name": {"type": "string", "description": "Application name, in any language"}}, ["name"]),
         launch_app, "action", label=lambda a: f"Ouverture de {a.get('name', '')}"),
    Tool("open_target",
         "Open a website URL, a file or a folder with the default application.",
         obj({"target": {"type": "string", "description": "URL (https://…) or path (~/Documents/…)"}}, ["target"]),
         open_target, "action", label=lambda a: f"Ouverture de {a.get('target', '')}"),
    Tool("list_windows", "List the open windows (application, title, virtual desktop).",
         obj({}), list_windows, "read", label=lambda a: "Liste des fenêtres ouvertes"),
    Tool("window_action",
         "Manage windows: focus, close, toggle fullscreen or floating, move a window to a virtual "
         "desktop (1-10), or switch to a virtual desktop. Without 'target' the active window is used.",
         obj({
             "action": {"type": "string", "enum": ["focus", "close", "fullscreen", "float",
                                                   "move_to_workspace", "switch_workspace"]},
             "target": {"type": "string", "description": "Part of the window's app name or title"},
             "workspace": {"type": "integer", "description": "Virtual desktop number 1-10"},
         }, ["action"]),
         window_action, "action", label=lambda a: "Gestion des fenêtres"),
    Tool("volume",
         "Change the sound volume: set to a percentage, turn up or down by a step, mute or unmute.",
         obj({
             "action": {"type": "string", "enum": ["set", "up", "down", "mute", "unmute"]},
             "percent": {"type": "integer", "description": "Target level (set) or step (up/down), 0-150"},
         }, ["action"]),
         volume, "action", label=lambda a: "Réglage du son"),
    Tool("brightness", "Change the screen brightness: set a percentage, or turn it up or down by a step.",
         obj({
             "action": {"type": "string", "enum": ["set", "up", "down"]},
             "percent": {"type": "integer", "description": "Target level (set) or step (up/down), 1-100"},
         }, ["action"]),
         brightness, "action", label=lambda a: "Réglage de la luminosité"),
    Tool("media_control", "Control the music or video player (play/pause, next, previous, stop) or get what is playing.",
         obj({"action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop", "status"]}}, ["action"]),
         media_control, "action", label=lambda a: "Contrôle du lecteur multimédia"),
    Tool("notify", "Show a desktop notification.",
         obj({"title": {"type": "string"}, "body": {"type": "string"}}, ["title"]),
         notify, "action", label=lambda a: "Notification"),
    Tool("set_reminder",
         "Schedule a reminder notification in N minutes (1 minute to 7 days). Call this when the "
         "user says 'rappelle-moi', 'remind me', or asks for a timer.",
         obj({"minutes": {"type": "integer", "description": "Delay in minutes"},
              "text": {"type": "string", "description": "Reminder text, in the user's language"}},
             ["minutes", "text"]),
         set_reminder, "action", label=lambda a: f"Rappel dans {a.get('minutes')} min"),
    Tool("take_screenshot",
         "Capture the user's screen and look at it. Call this when the user asks about what is on "
         "their screen, an error message they see, or wants help with the window in front of them.",
         obj({}), take_screenshot, "private", label=lambda a: "Capture de l'écran",
         summary=lambda a: "Envoyer une capture de ton écran à Claude (cloud) pour l'analyser",
         cloud_only=True),
    Tool("clipboard_read", "Read the text currently in the clipboard.",
         obj({}), clipboard_read, "private", label=lambda a: "Lecture du presse-papiers",
         summary=lambda a: "Envoyer le contenu de ton presse-papiers à Claude (cloud)"),
    Tool("clipboard_write", "Copy text to the clipboard.",
         obj({"text": {"type": "string"}}, ["text"]),
         clipboard_write, "action", label=lambda a: "Copie dans le presse-papiers"),
    Tool("network_status", "Get the network state: active connections (Wi-Fi name, wired) and whether Wi-Fi is on.",
         obj({}), network_status, "read", label=lambda a: "État du réseau"),
]
