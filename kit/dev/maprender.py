"""Render an FE4 map from WRAM + VRAM + CGRAM snapshots."""
import numpy as np
from PIL import Image


def load_cgram(state_path):
    st = open(state_path, 'rb').read()
    i = st.find(b'PPU:')
    ln = int(st[i + 4:i + 10])
    blk = st[i + 11:i + 11 + ln]
    pal = []
    for k in range(256):
        v = (blk[64 + 2 * k] << 8) | blk[64 + 2 * k + 1]
        pal.append((((v) & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3))
    return pal


def decode_tile4(vram, tile, namebase_words=0):
    a = (namebase_words * 2 + tile * 32) & 0xFFFF
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        b0, b1, b2, b3 = vram[a + 2 * y], vram[a + 2 * y + 1], vram[a + 16 + 2 * y], vram[a + 16 + 2 * y + 1]
        for x in range(8):
            s = 7 - x
            t[y, x] = ((b0 >> s) & 1) | (((b1 >> s) & 1) << 1) | (((b2 >> s) & 1) << 2) | (((b3 >> s) & 1) << 3)
    return t


def render_metatile(metadefs, vram, pal, k, cache):
    if k in cache:
        return cache[k]
    img = np.zeros((16, 16, 3), np.uint8)
    for q in range(4):
        e = metadefs[k * 4 + q]
        tile, p, hf, vf = e & 0x3FF, (e >> 10) & 7, e & 0x4000, e & 0x8000
        t = decode_tile4(vram, tile)
        if hf:
            t = t[:, ::-1]
        if vf:
            t = t[::-1, :]
        rgb = np.array([pal[p * 16 + c] for c in range(16)], np.uint8)[t]
        oy, ox = (q % 2) * 8, (q // 2) * 8
        img[oy:oy + 8, ox:ox + 8] = rgb
    cache[k] = img
    return img


def render_map(mapwords, width, height, metadefs, vram, pal, mask=0x3FF):
    out = np.zeros((height * 16, width * 16, 3), np.uint8)
    cache = {}
    for y in range(height):
        for x in range(width):
            k = mapwords[y * width + x] & mask
            out[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = render_metatile(metadefs, vram, pal, k, cache)
    return Image.fromarray(out)
