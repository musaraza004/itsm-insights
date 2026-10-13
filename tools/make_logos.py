"""Regenerate transparent logo variants from the originals in brand/.

Run: python tools/make_logos.py   (needs Pillow; not a package dependency)
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PAD = 12
LIGHT_TEXT = (241, 245, 249)


def unmix(rgb: np.ndarray) -> np.ndarray:
    """Colour-to-alpha against white: exact for anti-aliased edges drawn on white."""
    a = rgb.astype(float)
    alpha = (255 - a).max(axis=2) / 255.0
    alpha[alpha < 0.05] = 0
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    col = (a - 255 * (1 - alpha[..., None])) / safe
    return np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)


def outer_background(rgb: np.ndarray) -> np.ndarray:
    """Near-white pixels connected to the image border (not white details inside shapes)."""
    # .copy(): images from fromarray share numpy's read-only buffer, which floodfill can't write.
    mask = Image.fromarray(np.where(rgb.min(axis=2) > 200, 255, 0).astype(np.uint8), "L").copy()
    h, w = rgb.shape[:2]
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if mask.getpixel(xy) == 255:
            ImageDraw.floodfill(mask, xy, 128)
    return np.asarray(mask) == 128


def transparent(rgb: np.ndarray, mark_until: int) -> np.ndarray:
    """Mark (left of mark_until): only the outer background goes transparent, so white
    details inside the shape stay solid. Wordmark: plain colour-to-alpha."""
    out = unmix(rgb)
    bg = outer_background(rgb)
    solid = ~bg
    solid[:, mark_until:] = False
    out[solid, :3] = rgb[solid]
    out[solid, 3] = 255
    return out


def dark_variant(rgba: np.ndarray, text_from: int) -> np.ndarray:
    """Recolour dark, low-saturation wordmark text (navy/charcoal) to light for dark
    backgrounds, leaving saturated brand colours alone."""
    out = rgba.copy()
    rgb = out[..., :3].astype(int)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    dark = (rgb.mean(axis=2) < 85) & (spread < 100) & (out[..., 3] > 0)
    dark[:, :text_from] = False
    out[dark, :3] = LIGHT_TEXT
    return out


def save(arr: np.ndarray, rel: str, width: int, square: bool = False) -> None:
    img = Image.fromarray(arr, "RGBA")
    if square:
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = canvas
    img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img.save(ROOT / rel, optimize=True)
    print(rel, img.size)


def build(source: str, bbox: tuple, mark_right: int, text_left: int) -> tuple:
    rgb = np.asarray(Image.open(ROOT / "brand" / source).convert("RGB"))
    x0, y0, x1, y1 = bbox[0] - PAD, bbox[1] - PAD, bbox[2] + PAD, bbox[3] + PAD
    rgb = rgb[y0:y1, x0:x1]
    light = transparent(rgb, mark_right - x0 + PAD)
    return light, dark_variant(light, text_left - x0), mark_right - x0 + PAD


def main() -> None:
    light, dark, mark_w = build("itsm-insights-logo-original.png", (176, 232, 1368, 752), 553, 585)
    save(light, "docs/images/itsm-insights-logo-light.png", 720)
    save(dark, "docs/images/itsm-insights-logo-dark.png", 720)
    for rel, width in (
        ("web/assets/itsm-mark.png", 128),
        ("web/assets/favicon.png", 64),
        ("web/assets/apple-touch-icon.png", 180),
    ):
        save(light[:, :mark_w], rel, width, square=True)

    light, dark, _ = build("saan-technologies-logo-original.png", (125, 222, 1649, 672), 527, 550)
    save(light, "docs/images/saan-technologies-logo-light.png", 360)
    save(dark, "docs/images/saan-technologies-logo-dark.png", 360)
    save(light, "web/assets/saan-logo-light.png", 240)
    save(dark, "web/assets/saan-logo-dark.png", 240)


if __name__ == "__main__":
    main()
