"""FE4 compression (the format decoded by $80:AA02; $80:A9F2 is a variant entry).

Only two of the format's command types are needed to write valid streams:
  00-3F            literal run: copy the next (b & 0x3F) + 1 bytes
  80-BF xx         back-reference: copy ((b >> 2) & 0x0F) + 2 bytes from
                   `offset` bytes back, offset = ((b & 3) << 8) | xx  (1-1023)
  FF               end of stream
The game's own decompressor is used for decoding (via the 65816 emulator),
so every stream written here is checked against the real routine.
"""
from cpu65816 import CPU

MAX_LIT = 64
MIN_MATCH, MAX_MATCH = 2, 17
MAX_OFF = 1023


def compress(data):
    data = bytes(data)
    n = len(data)
    out = bytearray()
    lit = bytearray()
    # hash of 2-byte prefixes -> recent positions
    heads = {}

    def flush():
        nonlocal lit
        while lit:
            chunk = lit[:MAX_LIT]
            out.append(len(chunk) - 1)
            out.extend(chunk)
            lit = lit[MAX_LIT:]

    i = 0
    while i < n:
        best_len, best_off = 0, 0
        if i + 1 < n:
            key = data[i:i + 2]
            for j in reversed(heads.get(key, [])):
                off = i - j
                if off > MAX_OFF:
                    break
                ln = 0
                while ln < MAX_MATCH and i + ln < n and data[j + ln] == data[i + ln]:
                    ln += 1
                if ln > best_len:
                    best_len, best_off = ln, off
                    if ln == MAX_MATCH:
                        break
        if best_len >= 3 or (best_len == 2 and not lit):
            flush()
            out.append(0x80 | ((best_len - 2) << 2) | (best_off >> 8))
            out.append(best_off & 0xFF)
            step = best_len
        else:
            lit.append(data[i])
            if len(lit) == MAX_LIT:
                flush()
            step = 1
        for k in range(i, min(i + step, n - 1)):
            heads.setdefault(data[k:k + 2], []).append(k)
            if len(heads[data[k:k + 2]]) > 64:
                heads[data[k:k + 2]] = heads[data[k:k + 2]][-64:]
        i += step
    flush()
    out.append(0xFF)
    return bytes(out)


def decompress(rom, src_snes, max_steps=40_000_000, entry=0x80AA02):
    """Run the game's own decompressor. Returns the output bytes.

    $80:AA02 is the entry the game uses for maps and portraits. Kits up to v15 used $80:A9F2,
    which reads streams that cross a $xx:8000 boundary wrongly (the chapter 5 and endgame maps
    and the chapter 9 map tiles came out wrong); decompress_v15() keeps that for old projects."""
    c = CPU(rom)
    c.wram[0x10000:0x20000] = b'\xa5' * 0x10000      # sentinel fill to measure length
    c.wram[0xC8], c.wram[0xC9], c.wram[0xCA] = src_snes & 0xFF, (src_snes >> 8) & 0xFF, src_snes >> 16
    c.wram[0xCB] = c.wram[0xCC] = 0
    c.wram[0xCD] = 0x7F
    c.P, c.DB, c.D, c.S = 0x34, 0x80, 0, 0x1FF
    written = []
    orig_write = c.write

    def track(addr, v):
        if (addr >> 16) & 0xFF == 0x7F:
            written.append(addr & 0xFFFF)
        orig_write(addr, v)
    c.write = track
    c.call(entry, long=True, max_steps=max_steps)
    n = max(written) + 1 if written else 0
    return bytes(c.wram[0x10000:0x10000 + n])


def decompress_v15(rom, src_snes):
    """What kits up to v15 decoded (the $80:A9F2 entry): only to recognise old exports."""
    return decompress(rom, src_snes, entry=0x80A9F2)


def compressed_size(rom, src_snes):
    """Bytes consumed by the stream at src_snes (scan with the game's decoder)."""
    c = CPU(rom)
    c.wram[0xC8], c.wram[0xC9], c.wram[0xCA] = src_snes & 0xFF, (src_snes >> 8) & 0xFF, src_snes >> 16
    c.wram[0xCB] = c.wram[0xCC] = 0
    c.wram[0xCD] = 0x7F
    c.P, c.DB, c.D, c.S = 0x34, 0x80, 0, 0x1FF
    c.trace_reads = True
    c.call(0x80AA02, long=True, max_steps=40_000_000)
    offs = [fo for pc, fo in c.reads if 0x80A980 <= pc < 0x80AD30]
    return max(offs) - min(offs) + 1
