#!/usr/bin/env python3
"""Génère les images du thème GRUB et de l'écran de démarrage Plymouth de Nova.

GRUB :     surbrillance néon en 9 morceaux (select_*.png) + icônes des entrées
Plymouth : animation « anneau orbital » autour du logo (throbber-0001.png…)
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CYAN = (0, 240, 255)
VIOLET = (138, 92, 255)
MAGENTA = (255, 43, 214)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(t):
    return lerp(CYAN, VIOLET, t / 0.55) if t < 0.55 else lerp(VIOLET, MAGENTA, (t - 0.55) / 0.45)


def glow(img: Image.Image, radius: float, strength: int = 2) -> Image.Image:
    blurred = img.filter(ImageFilter.GaussianBlur(radius))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for _ in range(strength):
        out = Image.alpha_composite(out, blurred)
    return Image.alpha_composite(out, img)


# --- GRUB : surbrillance de l'entrée sélectionnée (9 morceaux étirables) -------------
def grub_selection(out: Path) -> None:
    size, corner, pad = 72, 18, 8
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = [pad, pad, size - pad - 1, size - pad - 1]
    draw.rounded_rectangle(box, radius=12, fill=(0, 240, 255, 34), outline=CYAN + (255,), width=2)
    img = glow(img, 4, 1)
    pieces = {
        "nw": (0, 0, corner, corner), "n": (corner, 0, size - corner, corner), "ne": (size - corner, 0, size, corner),
        "w": (0, corner, corner, size - corner), "c": (corner, corner, size - corner, size - corner),
        "e": (size - corner, corner, size, size - corner),
        "sw": (0, size - corner, corner, size), "s": (corner, size - corner, size - corner, size),
        "se": (size - corner, size - corner, size, size),
    }
    for name, crop in pieces.items():
        img.crop(crop).save(out / f"select_{name}.png")


# --- GRUB : panneau de verre sombre derrière le menu (lisibilité sur le fond néon) ------
def grub_menu_panel(out: Path) -> None:
    size, corner = 96, 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, size - 5, size - 5], radius=22, fill=(5, 6, 13, 205),
                           outline=(138, 92, 255, 110), width=2)
    img = glow(img, 3, 1)
    pieces = {
        "nw": (0, 0, corner, corner), "n": (corner, 0, size - corner, corner), "ne": (size - corner, 0, size, corner),
        "w": (0, corner, corner, size - corner), "c": (corner, corner, size - corner, size - corner),
        "e": (size - corner, corner, size, size - corner),
        "sw": (0, size - corner, corner, size), "s": (corner, size - corner, size - corner, size),
        "se": (size - corner, size - corner, size, size),
    }
    for name, crop in pieces.items():
        img.crop(crop).save(out / f"menu_{name}.png")


def icon_canvas(scale=4, size=48):
    return Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0)), scale, size


def finish_icon(img, size, out_path):
    img = glow(img, img.width / 40, 1).resize((size, size), Image.LANCZOS)
    img.save(out_path)


def icon_window(out_path: Path) -> None:
    """Icône neutre « fenêtre » pour l'autre système (Windows)."""
    img, s, size = icon_canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6 * s, 8 * s, 42 * s, 40 * s], radius=4 * s, outline=CYAN + (255,), width=3 * s)
    d.line([6 * s, 16 * s, 42 * s, 16 * s], fill=CYAN + (255,), width=3 * s)
    for i, x in enumerate((11, 16, 21)):
        d.ellipse([x * s - 2 * s, 12 * s - 2 * s, x * s + 2 * s, 12 * s + 2 * s], fill=gradient(i / 2) + (255,))
    finish_icon(img, size, out_path)


def icon_snapshots(out_path: Path) -> None:
    """Flèche circulaire « retour dans le temps » pour les instantanés."""
    img, s, size = icon_canvas()
    d = ImageDraw.Draw(img)
    d.arc([8 * s, 8 * s, 40 * s, 40 * s], start=-60, end=230, fill=MAGENTA + (255,), width=4 * s)
    d.polygon([(6 * s, 14 * s), (16 * s, 14 * s), (9 * s, 24 * s)], fill=MAGENTA + (255,))
    d.line([24 * s, 15 * s, 24 * s, 25 * s], fill=CYAN + (255,), width=3 * s)
    d.line([24 * s, 25 * s, 31 * s, 29 * s], fill=CYAN + (255,), width=3 * s)
    finish_icon(img, size, out_path)


def icon_firmware(out_path: Path) -> None:
    """Puce électronique pour l'accès au BIOS/UEFI."""
    img, s, size = icon_canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([13 * s, 13 * s, 35 * s, 35 * s], radius=3 * s, outline=VIOLET + (255,), width=3 * s)
    d.rectangle([19 * s, 19 * s, 29 * s, 29 * s], fill=CYAN + (200,))
    for k in (18, 24, 30):
        for x0, y0, x1, y1 in ((k, 6, k, 13), (k, 35, k, 42), (6, k, 13, k), (35, k, 42, k)):
            d.line([x0 * s, y0 * s, x1 * s, y1 * s], fill=VIOLET + (255,), width=2 * s)
    finish_icon(img, size, out_path)


def grub_assets() -> None:
    theme = ROOT / "grub" / "nova"
    icons = theme / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    grub_selection(theme)
    grub_menu_panel(theme)
    logo = Image.open(ROOT / "logo" / "nova-128.png").convert("RGBA").resize((48, 48), Image.LANCZOS)
    for name in ("nova", "gnu-linux", "linux", "arch"):
        logo.save(icons / f"{name}.png")
    icon_window(icons / "windows.png")
    icon_snapshots(icons / "snapshots.png")
    icon_firmware(icons / "efi.png")


# --- Plymouth : anneau orbital animé autour du logo -------------------------------------
def plymouth_frames(frames: int = 36, size: int = 220) -> None:
    out = ROOT / "plymouth" / "nova"
    out.mkdir(parents=True, exist_ok=True)
    scale = 3
    big = size * scale
    logo = Image.open(ROOT / "logo" / "nova-256.png").convert("RGBA").resize((int(big * 0.52),) * 2, Image.LANCZOS)
    for index in range(frames):
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        center, radius = big / 2, big * 0.42
        start = index * 360 / frames
        # traînée lumineuse qui s'estompe derrière la tête de l'arc
        for step in range(60):
            t = step / 59
            angle = start + t * 140
            alpha = int(255 * t ** 1.8)
            color = gradient(t) + (alpha,)
            a0, a1 = math.radians(angle), math.radians(angle + 3)
            x0, y0 = center + radius * math.cos(a0), center + radius * math.sin(a0)
            x1, y1 = center + radius * math.cos(a1), center + radius * math.sin(a1)
            d.line([x0, y0, x1, y1], fill=color, width=int(5 * scale))
        head = math.radians(start + 143)
        hx, hy = center + radius * math.cos(head), center + radius * math.sin(head)
        d.ellipse([hx - 7 * scale, hy - 7 * scale, hx + 7 * scale, hy + 7 * scale], fill=MAGENTA + (255,))
        img = glow(img, 6 * scale, 2)
        img.alpha_composite(logo, ((big - logo.width) // 2, (big - logo.height) // 2))
        img.resize((size, size), Image.LANCZOS).save(out / f"throbber-{index + 1:04d}.png")
    # éléments de la saisie du mot de passe (si le disque est chiffré un jour)
    entry = Image.new("RGBA", (320, 44), (0, 0, 0, 0))
    ImageDraw.Draw(entry).rounded_rectangle([1, 1, 318, 42], radius=12, fill=(10, 13, 26, 230), outline=CYAN + (255,), width=2)
    entry.save(out / "entry.png")
    bullet = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    ImageDraw.Draw(bullet).ellipse([1, 1, 12, 12], fill=CYAN + (255,))
    bullet.save(out / "bullet.png")
    lock = Image.open(ROOT / "logo" / "nova-64.png").convert("RGBA").resize((36, 36), Image.LANCZOS)
    lock.save(out / "lock.png")


if __name__ == "__main__":
    grub_assets()
    plymouth_frames()
    print("✓ images GRUB et Plymouth générées")
