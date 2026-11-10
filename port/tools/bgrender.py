"""Render a full SNES BG tilemap from a VRAM/CGRAM dump.
bgrender.py prefix tilemapWordAdr chrWordAdr bpp wide high out.png [--box x,y,w,h]
"""
import sys, struct
from PIL import Image, ImageDraw

def load(prefix):
    vram = open(prefix + '.vram', 'rb').read()
    cg = struct.unpack('<256H', open(prefix + '.cgram', 'rb').read())
    vw = struct.unpack('<32768H', vram)
    pal = [((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3) for c in cg]
    return vw, pal

def render(vw, pal, mapadr, chradr, bpp, wide, high):
    W = 64 if wide else 32; H = 64 if high else 32
    img = Image.new('RGB', (W * 8, H * 8), (255, 0, 255))
    px = img.load()
    for ty in range(H):
        for tx in range(W):
            # screens are 32x32 blocks: order 0 1 / 2 3
            sc = (tx // 32) + ((ty // 32) * (2 if wide else 1))
            e = vw[(mapadr + sc * 0x400 + (ty % 32) * 32 + (tx % 32)) & 0x7fff]
            tile = e & 0x3ff; p = (e >> 10) & 7; hf = e & 0x4000; vf = e & 0x8000
            base = chradr + tile * (4 * bpp)
            for y in range(8):
                sy = 7 - y if vf else y
                planes = [vw[(base + sy + 8 * (k // 2)) & 0x7fff] for k in range(0, bpp, 2)]
                for x in range(8):
                    sx = x if hf else 7 - x
                    c = 0
                    for k in range(bpp):
                        w = planes[k // 2]
                        c |= ((w >> (sx + (8 if k & 1 else 0))) & 1) << k
                    col = (0, 0, 0) if c == 0 else pal[(p << bpp) + c if bpp != 2 else p * 4 + c]
                    px[tx * 8 + x, ty * 8 + y] = col
    return img

if __name__ == '__main__':
    prefix, mapadr, chradr, bpp, wide, high, out = sys.argv[1:8]
    vw, pal = load(prefix)
    img = render(vw, pal, int(mapadr, 16), int(chradr, 16), int(bpp), wide == '1', high == '1')
    for a in sys.argv[8:]:
        if a.startswith('--box='):
            x, y, w, h = map(int, a[6:].split(','))
            d = ImageDraw.Draw(img)
            for dx in (0, img.width):
                for dy in (0, img.height):
                    d.rectangle([x - dx, y - dy, x - dx + w - 1, y - dy + h - 1], outline=(255, 255, 0))
                    d.rectangle([x + dx, y + dy, x + dx + w - 1, y + dy + h - 1], outline=(255, 255, 0))
    img.save(out)
