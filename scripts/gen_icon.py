"""Generate the application icon (PNG + multi-size ICO) without external deps.

Run:  python scripts/gen_icon.py
Writes: resources/icon.png  and  resources/icon.ico

Design: rounded-square brand-blue tile with a white checkmark.
Uses only numpy + stdlib (zlib/struct) so it stays offline and reproducible.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "resources"

# Brand palette (matches the QSS theme)
BG_TOP = np.array([61, 127, 232, 255], dtype=np.uint8)     # #3d7fe8
BG_BOTTOM = np.array([45, 111, 214, 255], dtype=np.uint8)  # #2d6fd6
CHECK = np.array([255, 255, 255, 255], dtype=np.uint8)


def _sdf_rounded_rect(px, py, size, radius):
    """Signed distance to a rounded rect centered at (size/2, size/2)."""
    hx = size / 2.0
    hy = size / 2.0
    qx = np.abs(px - hx) - (hx - radius)
    qy = np.abs(py - hy) - (hy - radius)
    ox = np.maximum(qx, 0.0)
    oy = np.maximum(qy, 0.0)
    outside = np.sqrt(ox ** 2 + oy ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside


def _dist_to_segment(px, py, ax, ay, bx, by):
    """Distance from points to segment AB (scaled to 256 canvas)."""
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    t = np.clip((apx * abx + apy * aby) / denom, 0.0, 1.0)
    cx = ax + t * abx
    cy = ay + t * aby
    return np.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def render(size: int) -> np.ndarray:
    """Render an RGBA tile of the given size."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)

    # Rounded-rect background with a vertical gradient.
    radius = size * 0.20
    d = _sdf_rounded_rect(xx, yy, size, radius)
    alpha = np.clip(0.5 - d, 0.0, 1.0)  # 1px anti-alias edge

    t = np.clip(yy / size, 0.0, 1.0)[..., None]
    bg = (BG_TOP * (1 - t) + BG_BOTTOM * t).astype(np.float64)

    # Checkmark: two thick segments.
    scale = size / 256.0
    line_w = 30.0 * scale
    d1 = _dist_to_segment(xx, yy, 74, 132, 116, 174)
    d2 = _dist_to_segment(xx, yy, 116, 174, 186, 96)
    check_alpha = np.clip(line_w / 2.0 - np.minimum(d1, d2) + 0.5, 0.0, 1.0)

    # Composite checkmark over the background.
    color = bg * (1 - check_alpha[..., None]) + CHECK.astype(np.float64) * check_alpha[..., None]

    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[..., 0:3] = np.clip(color[..., 0:3], 0, 255).astype(np.uint8)
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return rgba


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def encode_png(rgba: np.ndarray) -> bytes:
    """Encode an RGBA numpy array as a PNG byte string."""
    h, w, _ = rgba.shape
    raw = b"".join(
        b"\x00" + rgba[y].tobytes() for y in range(h)
    )
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def encode_ico(pngs: dict[int, bytes]) -> bytes:
    """Build an ICO embedding PNG images (Vista+ compatible)."""
    sizes = sorted(pngs.keys(), reverse=True)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    offset = 6 + 16 * len(sizes)
    blobs = b""
    for size in sizes:
        data = pngs[size]
        dim = 0 if size >= 256 else size  # 0 == 256
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset
        )
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main() -> None:
    RES.mkdir(exist_ok=True)

    sizes = (256, 64, 48, 32, 16)
    pngs = {s: encode_png(render(s)) for s in sizes}

    (RES / "icon.png").write_bytes(pngs[256])
    (RES / "icon.ico").write_bytes(encode_ico(pngs))
    print(f"[OK] wrote {RES / 'icon.png'} ({len(pngs[256])} bytes)")
    print(f"[OK] wrote {RES / 'icon.ico'} ({sum(len(p) for p in pngs.values())} bytes across {len(sizes)} sizes)")


if __name__ == "__main__":
    main()
