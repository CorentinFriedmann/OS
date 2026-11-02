"""Routage hybride : local (privé, gratuit) ou Claude (cloud) selon la demande."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Demandes qui méritent le cloud : web/actualité, analyse d'écran, code,
# rédaction ou raisonnement long. Le reste (piloter le PC, questions rapides)
# reste en local.
CLOUD_HINTS = re.compile(
    r"(cherche|recherche|sur internet|sur le web|en ligne|actualit|news|m[ée]t[ée]o|aujourd'hui|"
    r"ce soir|demain|cette semaine|derni[eè]re? version|prix|co[uû]te|cours de|horaires?|score|"
    r"[ée]cran|capture|que vois|regarde|erreur affich|"
    r"\bcode\b|script|programme|fonction|python|javascript|rust|bash|debug|bug|compil|"
    r"explique[- ]moi|en d[ée]tail|pourquoi|analyse|r[ée]sume|r[ée]dige|[ée]cris[- ](moi|un|une)|"
    r"traduis|lettre|e-?mail|plan d|compare|avantages|conseille)",
    re.IGNORECASE,
)
FORCE_PREFIX = re.compile(r"^\s*/(local|cloud)\b\s*", re.IGNORECASE)


@dataclass
class Decision:
    backend: str  # "local" | "cloud"
    reason: str
    text: str  # demande sans préfixe /local ou /cloud


def choose(text: str, config: dict, local_ok: bool, cloud_ok: bool,
           previous_backend: str | None = None, previous_age_s: float = 1e9) -> Decision:
    forced = FORCE_PREFIX.match(text)
    clean = FORCE_PREFIX.sub("", text, count=1) if forced else text
    strict = config.get("privacy", {}).get("strict_local", False)
    mode = forced.group(1).lower() if forced else config.get("mode", "auto")

    if strict or not cloud_ok:
        why = "confidentialité stricte" if strict else "cloud non configuré"
        return Decision("local", f"local ({why})", clean)
    if mode == "local":
        return Decision("local", "local (choisi)", clean)
    if mode == "cloud":
        return Decision("cloud", "cloud (choisi)", clean)
    if not local_ok:
        return Decision("cloud", "cloud (IA locale indisponible)", clean)
    if CLOUD_HINTS.search(clean) or len(clean) > 500:
        return Decision("cloud", "cloud (demande complexe ou besoin d'internet)", clean)
    if previous_backend == "cloud" and previous_age_s < 180 and len(clean) <= 160:
        return Decision("cloud", "cloud (suite de la discussion)", clean)
    return Decision("local", "local (rapide et privé)", clean)
