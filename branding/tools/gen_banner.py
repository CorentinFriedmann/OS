#!/usr/bin/env python3
"""Génère la bannière du README (docs/banner.png) : fond néon + logo + titre lumineux."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BRANDING = ROOT / "branding"


def neon_text(size: tuple[int, int], xy, text: str, font, color, glow_radius: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=color)
    glow = layer.filter(ImageFilter.GaussianBlur(glow_radius))
    wide = layer.filter(ImageFilter.GaussianBlur(glow_radius * 3))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for g in (wide, glow, glow):
        out = Image.alpha_composite(out, g)
    return Image.alpha_composite(out, layer)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "docs" / "banner.png")
    args = p.parse_args()

    W, H = 1600, 520
    bg = Image.open(BRANDING / "wallpapers" / "nova-city.jpg").convert("RGB")
    # Recadrage centré sur l'anneau et l'horizon
    scale = W / bg.width * 1.35
    bg = bg.resize((int(bg.width * scale), int(bg.height * scale)), Image.LANCZOS)
    left = (bg.width - W) // 2
    top = int(bg.height * 0.40) - H // 2
    banner = bg.crop((left, top, left + W, top + H)).convert("RGBA")
    # Voile sombre à gauche pour la lisibilité du titre
    veil = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(veil)
    for x in range(W):
        vd.line([(x, 0), (x, H)], fill=int(190 * max(0.0, 1 - x / (W * 0.75)) ** 1.2))
    banner = Image.composite(Image.new("RGBA", (W, H), (3, 4, 10, 255)), banner, veil)

    logo = Image.open(BRANDING / "logo" / "nova-512.png").convert("RGBA").resize((300, 300), Image.LANCZOS)
    glow = logo.filter(ImageFilter.GaussianBlur(18))
    banner.alpha_composite(glow, (70, (H - 300) // 2))
    banner.alpha_composite(logo, (70, (H - 300) // 2))

    title_font = ImageFont.truetype(str(BRANDING / "fonts/orbitron/Orbitron-Black.ttf"), 132)
    sub_font = ImageFont.truetype(str(BRANDING / "fonts/orbitron/Orbitron-Medium.ttf"), 34)
    title = neon_text((W, H), (410, 120), "NOVA OS", title_font, (230, 251, 255, 255), 10)
    # Liseré cyan -> magenta sous le titre
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for i in range(760):
        t = i / 759
        c = (int(0 + t * 255), int(240 - t * 197), int(255 - t * 41), 255)
        bd.line([(414 + i, 290), (414 + i, 294)], fill=c)
    bar = Image.alpha_composite(bar.filter(ImageFilter.GaussianBlur(6)), bar)
    sub = neon_text((W, H), (414, 322), "Arch  /  Hyprland  /  IA intégrée", sub_font, (0, 240, 255, 255), 6)
    for layer in (title, bar, sub):
        banner = Image.alpha_composite(banner, layer)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    banner.convert("RGB").save(args.out, optimize=True)
    print(f"✓ {args.out}")


if __name__ == "__main__":
    main()
