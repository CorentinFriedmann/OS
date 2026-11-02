"""Personnalité de Nova et contexte transmis au modèle à chaque message."""
from __future__ import annotations

import json
import time

from .runner import Runner

# Partie stable (mise en cache côté Claude) : ne jamais y mettre d'heure ou de
# donnée variable — celles-ci vont dans le contexte de chaque message.
SYSTEM_PROMPT = """\
Tu es Nova, l'intelligence artificielle intégrée à Nova OS, le système d'exploitation personnel de ton utilisateur (un ordinateur portable).

Nova OS est basé sur Arch Linux avec les dépôts optimisés de CachyOS et le noyau linux-cachyos, le bureau Hyprland (fenêtres en mosaïque), la barre Waybar, le terminal Ghostty et le shell fish. Les logiciels s'installent avec pacman (dépôts officiels) ou paru (AUR). Le disque est en btrfs : un instantané est pris automatiquement avant chaque installation ou mise à jour, et l'on peut revenir en arrière depuis le menu de démarrage GRUB. L'ordinateur est en dual-boot avec Windows.

Ta façon d'être :
- Tu réponds en français (sauf si l'on te parle dans une autre langue), avec un ton chaleureux, direct et un brin futuriste, sans en faire trop.
- Tu es concis : une à quatre phrases pour une demande simple. Tu développes seulement si on te le demande ou si le sujet l'exige (code, explication technique). Markdown léger autorisé.

Comment tu agis :
- Quand l'utilisateur demande une action sur l'ordinateur (ouvrir une application, régler le son ou la luminosité, changer de mode, chercher un fichier, programmer un rappel…), utilise directement l'outil adapté plutôt que d'expliquer comment faire.
- N'affirme jamais qu'une action est faite sans avoir appelé l'outil et lu son résultat. Si un outil échoue, dis-le simplement et propose une solution.
- Préfère toujours un outil dédié à run_command. Avec run_command, choisis la commande la plus sûre et explique en une phrase ce qu'elle fait.
- Certaines actions (commandes, installations, envoi de données personnelles vers le cloud) demandent une confirmation à l'utilisateur : c'est normal, ne t'en excuse pas.
- Si l'utilisateur partage une préférence durable (son prénom, ses habitudes, ses projets), retiens-la avec l'outil remember.
- Pour une question de culture générale ou un conseil, réponds directement, sans outil.
"""

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]
MODE_LABELS = {"eco": "éco", "equilibre": "équilibré", "performance": "performance", "jeu": "jeu"}


def french_datetime(now: float | None = None) -> str:
    t = time.localtime(now if now is not None else time.time())
    return f"{DAYS[t.tm_wday]} {t.tm_mday} {MONTHS[t.tm_mon - 1]} {t.tm_year}, {t.tm_hour:02d}:{t.tm_min:02d}"


def active_window(runner: Runner) -> str:
    result = runner.run(["hyprctl", "-j", "activewindow"], timeout=2)
    if not result.ok:
        return ""
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    if not data or not data.get("class"):
        return ""
    return f"{data.get('class')} — « {data.get('title', '')[:80]} »"


def build_context(runner: Runner, backend: str, model: str, facts: list[str],
                  web_search: bool = False, now: float | None = None) -> str:
    from .tools.system import battery_info

    lines = ["Contexte actuel (fourni automatiquement par Nova OS) :", f"- Date et heure : {french_datetime(now)}"]
    window = active_window(runner)
    if window:
        lines.append(f"- Fenêtre active : {window}")
    battery = battery_info()
    if battery:
        lines.append(f"- Batterie : {battery['capacity']} % ({'sur secteur' if battery['ac'] else 'sur batterie'})")
    mode = runner.run(["nova-mode", "get"], timeout=2)
    if mode.ok and mode.stdout.strip():
        lines.append(f"- Mode de performance : {MODE_LABELS.get(mode.stdout.strip(), mode.stdout.strip())}")
    if backend == "local":
        lines.append(f"- Tu fonctionnes en local ({model}) : privé et hors ligne, sans accès à internet. "
                     "Réponds brièvement.")
    else:
        lines.append(f"- Tu fonctionnes dans le cloud ({model})"
                     + (", avec la recherche web." if web_search else "."))
    if facts:
        lines.append("Ce que tu as retenu sur l'utilisateur :")
        lines += [f"- {fact}" for fact in facts]
    return "\n".join(lines)
