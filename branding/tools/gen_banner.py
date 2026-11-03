#!/usr/bin/env python3
"""Génère la bannière du README (docs/banner.png) : fond « verre » + carte de verre, logo et titre."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BRANDING = ROOT / "branding"
INTER = BRANDING / "fonts" / "inter" / "InterVariable.ttf"


def inter(size: int, weight: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(INTER), size)
    font.set_variation_by_name(weight)
    return font


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "banner.png")
    args = parser.parse_args()

    width, height = 1600, 520
    background = Image.open(BRANDING / "wallpapers" / "nova-verre.jpg").convert("RGB")
    scale = width / background.width * 1.25
    background = background.resize((int(background.width * scale), int(background.height * scale)), Image.LANCZOS)
    left = (background.width - width) // 2 - 120
    top = int(background.height * 0.42) - height // 2
    banner = background.crop((left, top, left + width, top + height)).convert("RGBA")

    # Carte de verre : flou de l'arrière-plan, voile clair, liseré fin
    card = (90, 110, 1110, 410)
    region = banner.crop(card).filter(ImageFilter.GaussianBlur(28))
    mask = Image.new("L", banner.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(card, radius=36, fill=255)
    frosted = banner.copy()
    frosted.paste(region, card[:2])
    frosted = Image.alpha_composite(frosted, Image.new("RGBA", banner.size, (255, 255, 255, 14)))
    banner = Image.composite(frosted, banner, mask)
    border = Image.new("RGBA", banner.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(card, radius=36, outline=(255, 255, 255, 34), width=2)
    banner = Image.alpha_composite(banner, border)

    logo = Image.open(BRANDING / "logo" / "nova-512.png").convert("RGBA").resize((200, 200), Image.LANCZOS)
    banner.alpha_composite(logo, (card[0] + 50, card[1] + 50))

    draw = ImageDraw.Draw(banner)
    title_font = inter(108, "SemiBold")
    x, y = card[0] + 290, card[1] + 48
    draw.text((x, y), "Nova OS", font=title_font, fill=(238, 241, 246, 255))
    bottom = draw.textbbox((x, y), "Nova OS", font=title_font)[3]
    draw.rounded_rectangle((x + 6, bottom + 18, x + 66, bottom + 22), radius=2, fill=(138, 180, 255, 255))
    draw.text((x + 6, bottom + 36), "Rapide, épuré, avec une IA intégrée",
              font=inter(34, "Regular"), fill=(164, 173, 189, 255))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    banner.convert("RGB").save(args.out, optimize=True)
    print(f"✓ {args.out}")


if __name__ == "__main__":
    main()
