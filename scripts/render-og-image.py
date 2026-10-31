#!/usr/bin/env python3
"""Render web/public/og-image.png (1200×630) for Open Graph previews."""

from __future__ import annotations

import math
from pathlib import Path

from fontTools.ttLib.woff2 import decompress as woff2_decompress
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "public" / "og-image.png"
FONT_CACHE = ROOT / ".cache" / "og-fonts"

BG = (245, 243, 236)
LINE = (221, 223, 211)
INK = (40, 46, 39)
MUTED = (131, 139, 120)
SUBTLE = (106, 115, 95)
ORANGE = (239, 90, 42)


def _ttf(woff2: Path) -> Path:
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    out = FONT_CACHE / woff2.with_suffix(".ttf").name
    if not out.exists():
        woff2_decompress(str(woff2), str(out))
    return out


def _font(relative: str, size: int) -> ImageFont.FreeTypeFont:
    path = WEB / "node_modules" / relative
    return ImageFont.truetype(str(_ttf(path)), size)


def _text_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, tracking: float
) -> float:
    if not text:
        return 0.0
    w = 0.0
    for i, ch in enumerate(text):
        box = draw.textbbox((0, 0), ch, font=font)
        w += box[2] - box[0]
        if i < len(text) - 1:
            w += tracking
    return w


def _draw_tracking(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    tracking: float,
    *,
    anchor: str = "ls",
) -> float:
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor=anchor)
        box = draw.textbbox((x, y), ch, font=font, anchor=anchor)
        x = box[2] + tracking
    return x


def _hexagon_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    return [
        (
            cx + r * math.cos(math.radians(60 * i - 30)),
            cy + r * math.sin(math.radians(60 * i - 30)),
        )
        for i in range(6)
    ]


def render() -> None:
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    margin = 44
    draw.rectangle(
        (margin, margin, w - margin, h - margin),
        outline=LINE,
        width=2,
    )

    # Decorative hexagon (kept clear of the top border)
    hex_cx, hex_cy, hex_r = w - margin - 95, margin + 148, 76
    draw.polygon(
        _hexagon_points(hex_cx, hex_cy, hex_r),
        outline=LINE,
        width=3,
    )
    dot = 7
    draw.polygon(
        [
            (hex_cx, hex_cy - dot),
            (hex_cx + dot, hex_cy),
            (hex_cx, hex_cy + dot),
            (hex_cx - dot, hex_cy),
        ],
        fill=ORANGE,
    )

    title_font = _font(
        "@fontsource/space-grotesk/files/space-grotesk-latin-600-normal.woff2", 78
    )
    tag_font = _font("@fontsource/dm-sans/files/dm-sans-latin-500-normal.woff2", 34)
    sub_font = _font("@fontsource/dm-sans/files/dm-sans-latin-400-normal.woff2", 24)
    url_font = _font("@fontsource/dm-sans/files/dm-sans-latin-400-normal.woff2", 20)

    title_baseline = 318
    title_x = margin + 76
    title_tracking = -3.2
    word = "synbios"
    after = _draw_tracking(
        draw,
        (title_x, title_baseline),
        word,
        title_font,
        INK,
        title_tracking,
    )
    draw.text((after, title_baseline), ".", font=title_font, fill=ORANGE, anchor="ls")

    tag = "Build together. Keep the evidence."
    tag_y = title_baseline + 36
    draw.text((title_x, tag_y), tag, font=tag_font, fill=INK)

    sub = "A workspace for accountable human and agent collaboration."
    draw.text((title_x, tag_y + 48), sub, font=sub_font, fill=MUTED)

    url = "moissanite-labs.github.io/synbios"
    url_box = draw.textbbox((0, 0), url, font=url_font)
    url_y = h - margin - (url_box[3] - url_box[1]) - 18
    draw.text((title_x, url_y), url, font=url_font, fill=SUBTLE)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="PNG", optimize=True)


if __name__ == "__main__":
    render()
