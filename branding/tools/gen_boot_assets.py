#!/usr/bin/env python3
"""Génère les images du menu de démarrage (GRUB) et de l'écran de démarrage (Plymouth).

Style « verre minimaliste » (palette : branding/palette.json) :
GRUB :     panneau de verre et surbrillance en 9 morceaux, icônes au trait fin
Plymouth : un arc fin qui tourne autour du logo (throbber-0001.png…)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PALETTE = json.loads((ROOT / "palette.json").read_text())


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


ACCENT = hex_rgb(PALETTE["accent"])
ACCENT_SOFT = hex_rgb(PALETTE["accent_soft"])
LAVENDER = hex_rgb(PALETTE["lavender"])
FG = hex_rgb(PALETTE["fg"])
BG0 = hex_rgb(PALETTE["bg0"])

NINE = ("nw", "n", "ne", "w", "c", "e", "sw", "s", "se")


def nine_slice(img: Image.Image, corner: int, out: Path, prefix: str) -> None:
    size = img.width
    boxes = {
        "nw": (0, 0, corner, corner), "n": (corner, 0, size - corner, corner), "ne": (size - corner, 0, size, corner),
        "w": (0, corner, corner, size - corner), "c": (corner, corner, size - corner, size - corner),
        "e": (size - corner, corner, size, size - corner),
        "sw": (0, size - corner, corner, size), "s": (corner, size - corner, size - corner, size),
        "se": (size - corner, size - corner, size, size),
    }
    for name in NINE:
        img.crop(boxes[name]).save(out / f"{prefix}_{name}.png")


def rounded(size: int, inset: int, radius: int, fill, outline, width: int = 2, scale: int = 4) -> Image.Image:
    """Rectangle arrondi anticrénelé (dessiné en grand puis réduit)."""
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle(
        [inset * scale, inset * scale, (size - inset) * scale - 1, (size - inset) * scale - 1],
        radius=radius * scale, fill=fill, outline=outline, width=width * scale)
    return big.resize((size, size), Image.LANCZOS)


# --- GRUB ---------------------------------------------------------------------------------
def grub_selection(out: Path) -> None:
    """Surbrillance de l'entrée choisie : verre teinté d'accent, liseré fin."""
    # Bords fins (10 px) : GRUB agrandit la surbrillance de la taille des bords
    img = rounded(40, 1, 9, fill=ACCENT + (34,), outline=ACCENT + (120,), width=1)
    nine_slice(img, 10, out, "select")


def grub_menu_panel(out: Path) -> None:
    """Panneau de verre sombre derrière le menu."""
    img = rounded(96, 2, 22, fill=(16, 19, 26, 196), outline=(255, 255, 255, 34), width=1)
    nine_slice(img, 32, out, "menu")


def canvas(scale: int = 4, size: int = 48):
    return Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0)), scale, size


def finish(img: Image.Image, size: int, path: Path) -> None:
    img.resize((size, size), Image.LANCZOS).save(path)


def icon_window(path: Path) -> None:
    """Icône neutre « fenêtre » pour l'autre système (Windows)."""
    img, s, size = canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8 * s, 10 * s, 40 * s, 38 * s], radius=5 * s, outline=FG + (230,), width=2 * s)
    d.line([8 * s, 17 * s, 40 * s, 17 * s], fill=FG + (230,), width=2 * s)
    for x in (13, 18):
        d.ellipse([x * s - int(1.6 * s), 13.5 * s - int(1.6 * s), x * s + int(1.6 * s), 13.5 * s + int(1.6 * s)],
                  fill=ACCENT + (255,))
    finish(img, size, path)


def icon_snapshots(path: Path) -> None:
    """Flèche circulaire « retour dans le temps » pour les instantanés."""
    img, s, size = canvas()
    d = ImageDraw.Draw(img)
    d.arc([9 * s, 9 * s, 39 * s, 39 * s], start=-60, end=230, fill=FG + (230,), width=2 * s)
    d.polygon([(7 * s, 14 * s), (16 * s, 14 * s), (10 * s, 23 * s)], fill=FG + (230,))
    d.line([24 * s, 16 * s, 24 * s, 25 * s], fill=ACCENT + (255,), width=2 * s)
    d.line([24 * s, 25 * s, 30 * s, 29 * s], fill=ACCENT + (255,), width=2 * s)
    finish(img, size, path)


def icon_firmware(path: Path) -> None:
    """Puce électronique pour l'accès au BIOS/UEFI."""
    img, s, size = canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14 * s, 14 * s, 34 * s, 34 * s], radius=3 * s, outline=FG + (230,), width=2 * s)
    d.rounded_rectangle([20 * s, 20 * s, 28 * s, 28 * s], radius=1 * s, fill=ACCENT + (230,))
    for k in (19, 24, 29):
        for x0, y0, x1, y1 in ((k, 8, k, 14), (k, 34, k, 40), (8, k, 14, k), (34, k, 40, k)):
            d.line([x0 * s, y0 * s, x1 * s, y1 * s], fill=FG + (200,), width=2 * s)
    finish(img, size, path)


def grub_assets() -> None:
    theme = ROOT / "grub" / "nova"
    icons = theme / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    grub_selection(theme)
    grub_menu_panel(theme)
    logo = Image.open(ROOT / "logo" / "nova-128.png").convert("RGBA")
    logo.resize((72, 72), Image.LANCZOS).save(theme / "logo.png")
    small = logo.resize((40, 40), Image.LANCZOS)
    for name in ("nova", "gnu-linux", "linux", "arch"):
        small.save(icons / f"{name}.png")
    icon_window(icons / "windows.png")
    icon_snapshots(icons / "snapshots.png")
    icon_firmware(icons / "efi.png")


# --- Plymouth -------------------------------------------------------------------------------
def plymouth_frames(frames: int = 36, size: int = 200) -> None:
    out = ROOT / "plymouth" / "nova"
    out.mkdir(parents=True, exist_ok=True)
    scale = 3
    big = size * scale
    logo = Image.open(ROOT / "logo" / "nova-256.png").convert("RGBA").resize((int(big * 0.46),) * 2, Image.LANCZOS)
    center, radius = big / 2, big * 0.44
    for index in range(frames):
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Piste très discrète, puis un arc fin dont la queue s'efface
        d.ellipse([center - radius, center - radius, center + radius, center + radius],
                  outline=(255, 255, 255, 22), width=int(2 * scale))
        start = index * 360 / frames
        for step in range(48):
            t = step / 47
            a0 = math.radians(start + t * 110)
            a1 = math.radians(start + t * 110 + 3)
            alpha = int(255 * t ** 1.6)
            color = tuple(int(ACCENT[i] + (ACCENT_SOFT[i] - ACCENT[i]) * t) for i in range(3)) + (alpha,)
            d.line([center + radius * math.cos(a0), center + radius * math.sin(a0),
                    center + radius * math.cos(a1), center + radius * math.sin(a1)],
                   fill=color, width=int(3 * scale))
        img.alpha_composite(logo, ((big - logo.width) // 2, (big - logo.height) // 2))
        img.resize((size, size), Image.LANCZOS).save(out / f"throbber-{index + 1:04d}.png")
    # Saisie d'un mot de passe (si le disque est chiffré un jour)
    entry = Image.new("RGBA", (320, 44), (0, 0, 0, 0))
    ImageDraw.Draw(entry).rounded_rectangle([1, 1, 318, 42], radius=12, fill=(22, 25, 33, 235),
                                            outline=(255, 255, 255, 40), width=1)
    entry.save(out / "entry.png")
    bullet = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    ImageDraw.Draw(bullet).ellipse([2, 2, 11, 11], fill=FG + (255,))
    bullet.save(out / "bullet.png")
    Image.open(ROOT / "logo" / "nova-64.png").convert("RGBA").resize((36, 36), Image.LANCZOS).save(out / "lock.png")


if __name__ == "__main__":
    grub_assets()
    plymouth_frames()
    print("✓ images GRUB et Plymouth générées")
