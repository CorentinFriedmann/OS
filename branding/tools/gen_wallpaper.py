#!/usr/bin/env python3
"""Génère le fond d'écran officiel de Nova OS (néon cyberpunk).

Scène : un canyon de gratte-ciel, une route-grille néon qui file vers
l'horizon, et l'anneau Nova qui se lève comme un soleil artificiel.

Tout est calculé « façon shader » avec numpy (champs de distance analytiques),
ce qui donne des bords lisses et des halos lumineux sans flou coûteux.

Usage :
    python3 gen_wallpaper.py --width 3840 --height 2160 --out nova-wallpaper.png
    python3 gen_wallpaper.py --variant lock  # version plus sombre (verrouillage / GRUB)

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
    return np.array([int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


CYAN = rgb(PALETTE["cyan"])
MAGENTA = rgb(PALETTE["magenta"])
VIOLET = rgb(PALETTE["violet"])
YELLOW = rgb(PALETTE["yellow"])
RED = rgb(PALETTE["red"])
WHITE = np.array([1.0, 1.0, 1.0], dtype=np.float32)


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return a * (1.0 - t[..., None]) + b * t[..., None]


def gradient3(t: np.ndarray) -> np.ndarray:
    """Dégradé signature Nova : cyan -> violet -> magenta."""
    t = np.clip(t, 0.0, 1.0)
    first = mix(CYAN, VIOLET, np.clip(t / 0.55, 0, 1))
    second = mix(VIOLET, MAGENTA, np.clip((t - 0.55) / 0.45, 0, 1))
    return np.where((t < 0.55)[..., None], first, second)


class Scene:
    def __init__(self, width: int, height: int, seed: int) -> None:
        self.W, self.H = width, height
        self.rng = np.random.default_rng(seed)
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        self.x, self.y = xs + 0.5, ys + 0.5
        self.img = np.zeros((height, width, 3), dtype=np.float32)
        self.horizon = 0.735 * height
        self.unit = height / 1000.0  # 1 unité = 1/1000 de la hauteur

    # ------------------------------------------------------------------ ciel
    def sky(self) -> None:
        H, y = self.H, self.y
        top = rgb("#03040b")
        mid = rgb("#0b0a24")
        low = rgb("#2a0f3f")
        t1 = smoothstep(0.0, 0.55 * H, y)
        t2 = smoothstep(0.45 * H, self.horizon, y)
        col = mix(mix(top, mid, t1), low, t2)
        # Halo violet diffus derrière l'anneau
        cx, cy = 0.5 * self.W, 0.60 * H
        d = np.hypot(self.x - cx, (self.y - cy) * 1.15)
        col += VIOLET[None, None, :] * (0.22 * np.exp(-d / (0.33 * H)))[..., None]
        col += MAGENTA[None, None, :] * (0.10 * np.exp(-d / (0.18 * H)))[..., None]
        sky_mask = (y < self.horizon)[..., None]
        self.img = np.where(sky_mask, col, self.img)

    def stars(self, count: int) -> None:
        W, H = self.W, self.H
        layer = Image.new("L", (W, H), 0)
        tint = Image.new("L", (W, H), 0)
        draw, tdraw = ImageDraw.Draw(layer), ImageDraw.Draw(tint)
        for _ in range(count):
            sx = float(self.rng.uniform(0, W))
            sy = float(self.rng.uniform(0, 0.62 * H) ** 1.0)
            b = float(self.rng.uniform(0.15, 1.0) ** 2.2)
            r = max(0.6, self.unit * float(self.rng.uniform(0.6, 1.6)))
            draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=int(255 * b))
            tdraw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=int(self.rng.uniform(0, 255)))
        glow = layer.filter(ImageFilter.GaussianBlur(2.5 * self.unit))
        a = (np.asarray(layer, np.float32) + 1.6 * np.asarray(glow, np.float32)) / 255.0
        t = np.asarray(tint, np.float32) / 255.0
        star_col = mix(rgb("#cfe9ff"), mix(CYAN, MAGENTA, t), np.full_like(t, 0.35))
        fade = 1.0 - smoothstep(0.35 * H, 0.70 * H, self.y)
        self.img += star_col * (a * fade * 0.9)[..., None]

    # ------------------------------------------------------- anneau + nova
    def nova_ring(self) -> None:
        H, u = self.H, self.unit
        cx, cy, R = 0.5 * self.W, 0.585 * H, 0.255 * H
        dx, dy = self.x - cx, self.y - cy
        dist = np.hypot(dx, dy)
        ang = np.degrees(np.arctan2(dy, dx))  # 0 = droite, -90 = haut
        # Ouverture de l'orbite en haut à droite, comme sur le logo : dans
        # l'ouverture, la distance est celle à l'extrémité d'arc la plus proche
        # (vrai champ de distance d'un arc à bouts ronds -> halo continu).
        g0, g1 = -45.0, -23.0
        in_gap = (ang > g0) & (ang < g1)
        e0 = (cx + R * math.cos(math.radians(g0)), cy + R * math.sin(math.radians(g0)))
        e1 = (cx + R * math.cos(math.radians(g1)), cy + R * math.sin(math.radians(g1)))
        d_end = np.minimum(np.hypot(self.x - e0[0], self.y - e0[1]), np.hypot(self.x - e1[0], self.y - e1[1]))
        d = np.where(in_gap, d_end, np.abs(dist - R))
        w = 4.2 * u
        core = 1.0 - smoothstep(w * 0.5 - 1.0, w * 0.5 + 1.0, d)
        glow = 0.55 * np.exp(-d / (9.0 * u)) + 0.28 * np.exp(-d / (42.0 * u))
        t = (self.x - (cx - R)) / (2 * R) * 0.85 + (self.y - (cy - R)) / (2 * R) * 0.15
        col = gradient3(t)
        intensity = core * 1.25 + glow
        self.img += col * intensity[..., None]
        # Satellite magenta dans l'ouverture
        a = math.radians(-34.0)
        sx, sy = cx + R * math.cos(a), cy + R * math.sin(a)
        ds = np.hypot(self.x - sx, self.y - sy)
        sat = (1.0 - smoothstep(6.5 * u - 1, 6.5 * u + 1, ds)) * 1.3 + 0.6 * np.exp(-ds / (14 * u))
        self.img += MAGENTA * sat[..., None]
        # Éclat de la nova (étoile à 4 branches, super-ellipse concave)
        S = 0.50 * R
        f = (np.abs(dx) / S) ** 0.5 + (np.abs(dy) / S) ** 0.5
        star = 1.0 - smoothstep(0.97, 1.03, f)
        star_glow = np.exp(-(np.maximum(f - 1.0, 0)) * 2.6)
        core_glow = np.exp(-np.hypot(dx, dy) / (20 * u))
        # Branches : cyan en haut/gauche -> magenta en bas/droite, cœur blanc
        tstar = np.clip(0.5 + dx / (2.0 * S) + dy / (2.6 * S), 0, 1)
        star_col = mix(gradient3(tstar), WHITE, np.clip(core_glow * 1.6, 0, 1))
        self.img += star_col * (star * 0.70 + star_glow * 0.45)[..., None]
        self.img += WHITE * (core_glow * 0.85)[..., None]
        # Reflets anamorphiques (lens flare horizontal marqué, vertical discret)
        flare_h = np.exp(-np.abs(dy) / (1.3 * u)) * np.exp(-np.abs(dx) / (0.36 * self.W))
        flare_v = np.exp(-np.abs(dx) / (1.0 * u)) * np.exp(-np.abs(dy) / (0.09 * H))
        self.img += mix(CYAN, WHITE, np.full_like(dx, 0.4)) * (0.50 * flare_h + 0.18 * flare_v)[..., None]

    # --------------------------------------------------------------- ville
    def _buildings(self, layer: str) -> list[tuple[float, float, float, float]]:
        W, H, hz = self.W, self.H, self.horizon
        out = []
        x = -0.02 * W
        while x < 1.02 * W:
            if layer == "far":
                bw = float(self.rng.uniform(0.012, 0.035)) * W
                center = abs((x + bw / 2) / W - 0.5) * 2  # 0 au centre, 1 aux bords
                h = float(self.rng.uniform(0.035, 0.13)) * H * (0.55 + 0.9 * center)
                base = hz + 1
            else:
                bw = float(self.rng.uniform(0.03, 0.075)) * W
                center = abs((x + bw / 2) / W - 0.5) * 2
                if center < 0.50:  # on dégage le centre pour voir la route et l'anneau
                    x += bw
                    continue
                h = (0.22 + 0.55 * (center - 0.50) / 0.50 + float(self.rng.uniform(-0.04, 0.07))) * H
                base = H + 1
            top = base - h
            out.append((x, top, x + bw, base))
            x += bw * float(self.rng.uniform(0.92, 1.12))
        return out

    def city(self) -> None:
        W, H, u = self.W, self.H, self.unit
        far = self._buildings("far")
        near = self._buildings("near")

        def silhouette(rects, fill_hex: str, rim_hex: str, rim_strength: float) -> np.ndarray:
            mask = Image.new("L", (W, H), 0)
            draw = ImageDraw.Draw(mask)
            for x0, y0, x1, y1 in rects:
                draw.rectangle([x0, y0, x1, y1], fill=255)
            m = np.asarray(mask, np.float32) / 255.0
            # Liseré lumineux sur les toits et arêtes (rim light venant de l'anneau)
            edges = np.asarray(mask.filter(ImageFilter.FIND_EDGES), np.float32) / 255.0
            rim = np.asarray(Image.fromarray((edges * 255).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(1.2 * u)), np.float32) / 255.0
            fill = rgb(fill_hex)
            self.img = mix(self.img, np.broadcast_to(fill, self.img.shape), m)
            self.img += rgb(rim_hex) * (rim * rim_strength * m)[..., None]
            return m

        far_mask = silhouette(far, "#0c0d23", PALETTE["violet"], 0.9)
        # Brume néon entre les deux plans
        haze = np.exp(-np.abs(self.y - self.horizon) / (0.05 * H)) * (self.y < self.horizon)
        self.img += (MAGENTA * 0.10 + VIOLET * 0.10) * haze[..., None]
        self.windows(far, density=0.10, scale=0.6, strength=0.55)
        near_mask = silhouette(near, "#03040a", PALETTE["cyan"], 0.55)
        self.windows(near, density=0.16, scale=1.0, strength=1.0)
        self.signs(near)
        self.antennas(near)
        self.city_mask = np.clip(far_mask + near_mask, 0, 1)

    def windows(self, rects, density: float, scale: float, strength: float) -> None:
        W, H, u = self.W, self.H, self.unit
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(layer)
        palette = [CYAN, MAGENTA, YELLOW, rgb("#9fd8ff"), VIOLET]
        weights = np.array([0.34, 0.20, 0.10, 0.28, 0.08])
        ww, wh = 2.2 * u * scale, 3.4 * u * scale
        gx, gy = 6.0 * u * scale, 9.0 * u * scale
        for x0, y0, x1, y1 in rects:
            cols = int((x1 - x0 - gx) / gx)
            rows = int((min(y1, H) - y0 - gy) / gy)
            # Chaque immeuble a sa propre ambiance : une couleur dominante,
            # des étages entiers éteints, une densité variable.
            main = palette[int(self.rng.choice(len(palette), p=weights))]
            accent = palette[int(self.rng.choice(len(palette), p=weights))]
            local = density * float(self.rng.uniform(0.4, 1.5))
            for r in range(max(rows, 0)):
                if self.rng.random() < 0.35:
                    continue  # étage éteint
                for c in range(max(cols, 0)):
                    if self.rng.random() > local:
                        continue
                    col = main if self.rng.random() < 0.8 else accent
                    b = float(self.rng.uniform(0.35, 1.0))
                    px, py = x0 + gx * (c + 0.8), y0 + gy * (r + 0.9)
                    color = tuple(int(255 * min(1.0, v * b)) for v in col)
                    draw.rectangle([px, py, px + ww, py + wh], fill=color)
        arr = np.asarray(layer, np.float32) / 255.0
        glow = np.asarray(layer.filter(ImageFilter.GaussianBlur(5 * u * scale)), np.float32) / 255.0
        self.img += (arr * 0.9 + glow * 1.6) * strength

    def signs(self, rects) -> None:
        W, H, u = self.W, self.H, self.unit
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for x0, y0, x1, y1 in rects:
            if self.rng.random() < 0.55:
                continue
            col = [CYAN, MAGENTA, VIOLET][int(self.rng.integers(0, 3))]
            color = tuple(int(255 * v) for v in col)
            if self.rng.random() < 0.6:  # enseigne verticale
                sx = float(self.rng.uniform(x0 + 0.15 * (x1 - x0), x1 - 0.2 * (x1 - x0)))
                sy = float(self.rng.uniform(y0 + 0.05 * (y1 - y0), y0 + 0.45 * (y1 - y0)))
                draw.rectangle([sx, sy, sx + 2.6 * u, sy + float(self.rng.uniform(40, 120)) * u], fill=color)
            else:  # bandeau horizontal
                sy = float(self.rng.uniform(y0 + 0.08 * (y1 - y0), y0 + 0.5 * (y1 - y0)))
                draw.rectangle([x0 + 0.1 * (x1 - x0), sy, x1 - 0.1 * (x1 - x0), sy + 2.2 * u], fill=color)
        arr = np.asarray(layer, np.float32) / 255.0
        g1 = np.asarray(layer.filter(ImageFilter.GaussianBlur(4 * u)), np.float32) / 255.0
        g2 = np.asarray(layer.filter(ImageFilter.GaussianBlur(18 * u)), np.float32) / 255.0
        self.img += arr * 1.2 + g1 * 1.8 + g2 * 1.4

    def antennas(self, rects) -> None:
        W, H, u = self.W, self.H, self.unit
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        lights = Image.new("RGB", (W, H), (0, 0, 0))
        draw, ldraw = ImageDraw.Draw(layer), ImageDraw.Draw(lights)
        for x0, y0, x1, y1 in rects:
            if self.rng.random() < 0.6 or y0 > 0.65 * H:
                continue
            ax = float(self.rng.uniform(x0 + 0.3 * (x1 - x0), x1 - 0.3 * (x1 - x0)))
            ah = float(self.rng.uniform(25, 70)) * u
            draw.rectangle([ax, y0 - ah, ax + 1.6 * u, y0], fill=(4, 5, 12))
            r = 2.6 * u
            ldraw.ellipse([ax - r, y0 - ah - r, ax + r, y0 - ah + r], fill=tuple(int(255 * v) for v in RED))
        mask = np.asarray(layer.convert("L"), np.float32) > 0
        self.img[mask] = rgb("#04050c")
        arr = np.asarray(lights, np.float32) / 255.0
        glow = np.asarray(lights.filter(ImageFilter.GaussianBlur(7 * u)), np.float32) / 255.0
        self.img += arr * 1.3 + glow * 2.2

    # -------------------------------------------------------------- route
    def floor(self) -> None:
        W, H, u, hz = self.W, self.H, self.unit, self.horizon
        below = self.y > hz
        depth = np.where(below, (self.y - hz) / (H - hz), 1.0)  # 0 horizon -> 1 bas
        base = mix(rgb("#0c0820"), rgb("#020206"), np.clip(depth ** 0.6, 0, 1))
        # Grille perspective : z = 1/depth, x monde = (x - xc) * z
        z = 1.0 / np.maximum(depth, 1e-3)
        xc = 0.5 * W
        wx = (self.x - xc) / (0.09 * H) * z
        wz = z * 1.0
        # Anti-aliasing approximatif via la dérivée écran des coordonnées monde
        dwx = np.abs(np.gradient(wx, axis=1)) + 1e-4
        dwz = np.abs(np.gradient(wz, axis=0)) + 1e-4
        lx = np.abs(wx - np.round(wx)) / dwx
        lz = np.abs(wz - np.round(wz)) / dwz
        line_x = np.exp(-lx * 0.9)
        line_z = np.exp(-lz * 0.9)
        fade_far = smoothstep(0.02, 0.32, depth)
        fade_side = np.exp(-np.abs(self.x - xc) / (0.55 * W))
        grid = np.maximum(line_x * np.clip(1.6 / (dwx * 40), 0, 1), line_z) * fade_far * fade_side
        col = mix(MAGENTA, VIOLET, np.clip(depth, 0, 1)) * 0.95
        # Reflet de l'anneau et de l'horizon sur la route
        ref = np.exp(-np.abs(self.x - xc) / (0.12 * W)) * np.exp(-(self.y - hz) / (0.10 * H))
        horizon_line = np.exp(-np.abs(self.y - hz) / (2.2 * u))
        floor_col = base + col * grid[..., None] * 0.85
        floor_col += mix(VIOLET, MAGENTA, np.full_like(ref, 0.4)) * (ref * 0.35)[..., None]
        self.img = np.where(below[..., None] & (self.city_mask[..., None] < 0.5), floor_col, self.img)
        self.img += mix(CYAN, WHITE, np.full_like(ref, 0.3)) * (horizon_line * 0.9 * (1 - self.city_mask))[..., None]
        self.img += MAGENTA * (np.exp(-np.abs(self.y - hz) / (14 * u)) * 0.35 * (1 - self.city_mask))[..., None]

    # -------------------------------------------------------- finitions
    def finish(self, variant: str) -> Image.Image:
        W, H = self.W, self.H
        # Vignette
        nx, ny = (self.x / W - 0.5) * 2, (self.y / H - 0.5) * 2
        vig = 1.0 - 0.45 * np.clip((nx ** 2 * 0.6 + ny ** 2 * 0.9), 0, 1.4) ** 1.3
        img = self.img * vig[..., None]
        if variant == "lock":
            img *= 0.55
        # Tone mapping doux (évite les aplats brûlés tout en gardant le punch néon)
        img = 1.0 - np.exp(-img * 1.35)
        img = np.clip(img, 0, 1) ** (1 / 1.08)
        # Grain très léger pour éviter les bandes dans les dégradés
        img += self.rng.normal(0, 1.2 / 255.0, img.shape).astype(np.float32)
        out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
        return Image.fromarray(out, "RGB")

    def render(self, variant: str = "default") -> Image.Image:
        self.sky()
        self.stars(int(0.00016 * self.W * self.H))
        self.nova_ring()
        self.city()
        self.floor()
        return self.finish(variant)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--width", type=int, default=3840)
    p.add_argument("--height", type=int, default=2160)
    p.add_argument("--seed", type=int, default=2077)
    p.add_argument("--variant", choices=["default", "lock"], default="default")
    p.add_argument("--out", type=Path, default=Path("nova-wallpaper.png"))
    args = p.parse_args()
    image = Scene(args.width, args.height, args.seed).render(args.variant)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(args.out, quality=92, optimize=True, progressive=True)
    else:
        image.save(args.out, optimize=True)
    print(f"✓ {args.out} ({args.width}x{args.height}, variante {args.variant})")


if __name__ == "__main__":
    main()
