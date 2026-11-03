#!/usr/bin/env python3
"""Génère les fonds d'écran officiels de Nova OS (style « verre minimaliste »).

Scène : un fond graphite profond, quelques grandes lumières douces (bleu glacier,
lavande) très floues, vues à travers deux plaques de verre dépoli posées en biais.
Dans les plaques, la lumière est plus diffuse et légèrement éclaircie ; leurs bords
portent un liseré lumineux très fin. Un grain discret évite les dégradés en escalier.

Usage :
    python3 gen_wallpaper.py --width 3840 --height 2160 --out nova-verre.jpg
    python3 gen_wallpaper.py --variant lock   # plus sombre et plus flou (verrouillage, GRUB)
    python3 gen_wallpaper.py --seed 7         # autre composition et autres teintes

Dépendances : numpy, Pillow.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
PALETTE = json.loads((HERE.parent / "palette.json").read_text())


def rgb(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


BG0, BG1 = rgb(PALETTE["bg0"]), rgb(PALETTE["bg1"])
ACCENT, LAVENDER, TEAL = rgb(PALETTE["accent"]), rgb(PALETTE["lavender"]), rgb(PALETTE["teal"])


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def lights(w: int, h: int, rng: np.random.Generator, variant: str) -> np.ndarray:
    """Champ de lumière (linéaire) : un ruban lumineux courbe, son halo, et un éclat discret."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x /= w
    y /= h
    first, second = (TEAL, ACCENT) if variant == "teal" else (ACCENT, LAVENDER)
    phase = rng.uniform(0, 2 * math.pi)
    # Ruban : une courbe douce qui monte du bas-gauche vers le haut-droit
    curve = 0.80 - 0.62 * x + 0.07 * np.sin(2.1 * math.pi * x + phase)
    d = np.abs(y - curve)
    t = np.clip(x, 0, 1)[..., None]
    color = srgb_to_linear(first) * (1 - t) + srgb_to_linear(second) * t
    core = np.exp(-d ** 2 / (2 * 0.035 ** 2))
    halo = np.exp(-d ** 2 / (2 * 0.16 ** 2))
    # Le ruban s'estompe aux deux extrémités, plus intense au centre-droit
    along = np.exp(-((x - 0.62) ** 2) / (2 * 0.33 ** 2))
    field = color * ((core * 1.15 + halo * 0.35) * along)[..., None]
    # Second filet, plus fin et plus pâle, décalé
    curve2 = curve + 0.09 + 0.03 * np.sin(3.3 * math.pi * x + phase * 0.7)
    field += srgb_to_linear(second) * (np.exp(-np.abs(y - curve2) ** 2 / (2 * 0.012 ** 2)) * along * 0.35)[..., None]
    # Éclat lointain en haut à gauche
    d2 = ((x - 0.16) * w / h) ** 2 + (y - 0.18) ** 2
    field += srgb_to_linear(second) * (np.exp(-d2 / (2 * 0.12 ** 2)) * 0.18)[..., None]
    return field


def rounded_rect_mask(size, box, radius, angle_deg, scale=2) -> Image.Image:
    """Masque d'une plaque de verre (rectangle arrondi tourné), anticrénelé."""
    w, h = size
    big = Image.new("L", (w * scale, h * scale), 0)
    x0, y0, x1, y1 = (v * scale for v in box)
    ImageDraw.Draw(big).rounded_rectangle([x0, y0, x1, y1], radius=radius * scale, fill=255)
    big = big.rotate(angle_deg, resample=Image.BICUBIC, center=((x0 + x1) / 2, (y0 + y1) / 2))
    return big.resize((w, h), Image.LANCZOS)


def render(width: int, height: int, variant: str, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    # Travail en basse résolution pour les lumières (elles sont lisses), puis agrandissement
    lw, lh = max(320, width // 4), max(180, height // 4)
    y = np.linspace(0, 1, lh, dtype=np.float32)[:, None, None]
    base = srgb_to_linear(BG0) * (1 - y) + srgb_to_linear(BG1) * y
    base = np.broadcast_to(base, (lh, lw, 3)).copy()
    light = lights(lw, lh, rng, "teal" if seed % 2 == 0 and variant != "lock" else variant)
    strength = 0.08 if variant == "lock" else 0.13
    scene = base + light * strength

    # Vignettage doux
    yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
    r = np.sqrt(((xx / lw - 0.5) * 1.2) ** 2 + ((yy / lh - 0.5)) ** 2)
    scene *= (1 - 0.35 * np.clip(r, 0, 1) ** 2)[..., None]
    low = Image.fromarray((linear_to_srgb(scene) * 255).astype(np.uint8))
    full = np.asarray(low.resize((width, height), Image.BICUBIC), dtype=np.float32) / 255

    if variant != "lock":
        # Deux plaques de verre dépoli : intérieur plus diffus et éclairci, liseré lumineux
        frosted = np.asarray(low.filter(ImageFilter.GaussianBlur(lw / 14)).resize((width, height), Image.BICUBIC),
                             dtype=np.float32) / 255
        frosted = np.clip(frosted * 1.06 + 0.012, 0, 1)
        panes = [
            ((0.58, 0.20, 0.88, 0.70), 0.028, -8.0, 0.92),
            ((0.18, 0.62, 0.30, 0.83), 0.022, -8.0, 0.70),
        ]
        for (fx0, fy0, fx1, fy1), fr, angle, opacity in panes:
            box = (fx0 * width, fy0 * height, fx1 * width, fy1 * height)
            mask = rounded_rect_mask((width, height), box, fr * width, angle)
            m = np.asarray(mask, dtype=np.float32)[..., None] / 255 * opacity
            # Reflet : le haut de la plaque capte un peu plus de lumière
            gy = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
            sheen = 0.022 * np.clip(1 - (gy - fy0) / max(fy1 - fy0, 1e-3), 0, 1) ** 2
            full = full * (1 - m) + (frosted + sheen) * m
            # Liseré : contour fin, plus lumineux en haut à gauche (lumière rasante)
            edge = np.asarray(mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.2)),
                              dtype=np.float32) / 255
            gy, gx = np.mgrid[0:height, 0:width].astype(np.float32)
            rake = np.clip(1.15 - (gx / width - fx0) * 0.9 - (gy / height - fy0) * 1.3, 0.15, 1.0)
            full += (edge * rake * 0.16 * opacity)[..., None]
    else:
        full *= 0.82

    # Grain (anti-escaliers)
    full += rng.normal(0, 1.1 / 255, full.shape).astype(np.float32)
    return Image.fromarray((np.clip(full, 0, 1) * 255 + 0.5).astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--variant", choices=["default", "lock"], default="default")
    parser.add_argument("--seed", type=int, default=2077)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    image = render(args.width, args.height, args.variant, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.suffix.lower() in (".jpg", ".jpeg"):
        image.save(args.out, quality=92, optimize=True, progressive=True, subsampling=0)
    else:
        image.save(args.out, optimize=True)
    print(f"✓ {args.out} ({args.width}x{args.height}, {args.variant}, graine {args.seed})")


if __name__ == "__main__":
    main()
