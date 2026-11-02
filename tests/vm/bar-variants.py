#!/usr/bin/env python3
"""Diagnostic de la barre (test en VM uniquement) : écrit des variantes de Waybar.

  bar-variants.py DOSSIER_WAYBAR_NOVA RACINE_DU_SYSTÈME_INSTALLÉ DOSSIER_DE_SORTIE

Chaque variante retire un élément de la configuration Nova (ou part de celle de
Waybar par défaut, qui s'affiche dans la VM). Lancées ensemble dans la session de
test, elles montrent dans le journal (« wb-<variante> ») lesquelles s'affichent.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


def load_jsonc(path: Path) -> dict:
    """JSON avec commentaires // et /* */ (hors chaînes) et virgules finales tolérées."""
    text, out, i, in_string = path.read_text(encoding="utf-8"), [], 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\":
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = len(text) if i < 0 else i
            continue
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 2
            continue
        else:
            out.append(char)
        i += 1
    cleaned = "".join(out)
    import re
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    data = json.loads(cleaned)
    return data[0] if isinstance(data, list) else data


def main(argv: list[str]) -> int:
    nova_dir, target, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    out.mkdir(parents=True, exist_ok=True)
    nova = load_jsonc(nova_dir / "config.jsonc")
    nova_css = (nova_dir / "style.css").read_text(encoding="utf-8")
    default_dir = target / "etc/xdg/waybar"
    default_cfg = default_dir / "config.jsonc"
    if not default_cfg.exists():
        default_cfg = default_dir / "config"
    default = load_jsonc(default_cfg)
    default_css = (default_dir / "style.css").read_text(encoding="utf-8")

    variants: dict[str, tuple[dict, str]] = {
        "defaut": (default, default_css),
        "defaut-style-nova": (default, nova_css),
        "nova": (nova, nova_css),
        "nova-style-defaut": (nova, default_css),
    }
    no_reload = copy.deepcopy(nova)
    no_reload["reload_style_on_change"] = False
    variants["sans-rechargement"] = (no_reload, nova_css)
    no_margin = copy.deepcopy(nova)
    for key in ("margin-top", "margin-left", "margin-right", "margin-bottom", "margin"):
        no_margin.pop(key, None)
    variants["sans-marges"] = (no_margin, nova_css)
    right = nova.get("modules-right", [])
    groups = {
        "gauche": (nova.get("modules-left", []), []),
        "droite-1": ([], right[:4]),
        "droite-2": ([], right[4:9]),
        "droite-3": ([], right[9:]),
    }
    for name, (left, right_part) in groups.items():
        cfg = copy.deepcopy(nova)
        cfg["modules-left"], cfg["modules-center"], cfg["modules-right"] = left, ["clock"], right_part
        variants[name] = (cfg, nova_css)

    for name, (cfg, css) in variants.items():
        (out / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{name}.css").write_text(css, encoding="utf-8")
    (out / "variantes").write_text(" ".join(variants) + "\n", encoding="utf-8")
    for name, (left, right_part) in groups.items():
        print(f"{name} : {' '.join(left + ['clock'] + right_part)}")
    print(f"{len(variants)} variantes : {' '.join(variants)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
