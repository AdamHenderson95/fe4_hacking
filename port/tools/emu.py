"""Snes9x libretro reference harness (ctypes). Same movie format as lsrun."""
import ctypes as C, sys, os

RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_GET_LOG_INTERFACE = 27

# libretro joypad ids: B Y SELECT START UP DOWN LEFT RIGHT A X L R
BTN = "BYsSUDLRAXlr"

class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIOB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

DEFAULT_CORE = os.path.join(os.path.dirname(__file__), '..', 'ext', 'snes9x', 'libretro', 'snes9x_libretro.so')

def parse_movie(path):
    ev = []
    if path and os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line[0] == '#': continue
            p = line.split()
            m = 0
            for ch in (p[1] if len(p) > 1 else '-'):
                if ch in BTN: m |= 1 << BTN.index(ch)
            ev.append((int(p[0]), m))
    return ev

class Emu:
    def __init__(self, rom, core=DEFAULT_CORE):
        self.lib = C.CDLL(os.path.abspath(core))
        self.held = 0
        self.frame = None
        self.fmt = 0
        self._cbs = [ENV(self._env), VIDEO(self._video), AUDIO(lambda l, r: None),
                     AUDIOB(lambda d, n: n), POLL(lambda: None), STATE(self._state)]
        L = self.lib
        L.retro_set_environment(self._cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self._cbs[1]); L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3]); L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        data = open(rom, 'rb').read()
        self._rom = C.create_string_buffer(data, len(data))
        gi = GameInfo(rom.encode(), C.cast(self._rom, C.c_void_p), len(data), None)
        assert L.retro_load_game(C.byref(gi))
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        self.frames = 0

    def _env(self, cmd, data):
        if cmd == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]; return True
        if cmd in (RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY):
            C.cast(data, C.POINTER(C.c_char_p))[0] = b"/tmp"; return True
        return False

    def _video(self, data, w, h, pitch):
        if data:
            self.frame = (C.string_at(data, pitch * h), w, h, pitch)

    def _state(self, port, dev, idx, id_):
        if port == 0 and dev == 1:
            return 1 if (self.held >> id_) & 1 else 0
        return 0

    def run(self, n=1):
        for _ in range(n):
            self.lib.retro_run(); self.frames += 1

    def mem(self, kind):
        p = self.lib.retro_get_memory_data(kind); n = self.lib.retro_get_memory_size(kind)
        return C.string_at(p, n) if p else b''

    def wram(self): return self.mem(2)
    def sram(self): return self.mem(0)

    def poke(self, addr, data):
        p = self.lib.retro_get_memory_data(2)
        C.memmove(p + addr, data, len(data))

    def save_state(self):
        n = self.lib.retro_serialize_size(); b = C.create_string_buffer(n)
        assert self.lib.retro_serialize(b, n); return b.raw

    def load_state(self, s):
        b = C.create_string_buffer(s, len(s)); assert self.lib.retro_unserialize(b, len(s))

    def screenshot(self, path):
        data, w, h, pitch = self.frame
        out = bytearray()
        for y in range(h):
            row = data[y * pitch:(y + 1) * pitch]
            for x in range(w):
                if self.fmt == 1:  # XRGB8888
                    b, g, r = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
                else:  # RGB565
                    v = row[x * 2] | (row[x * 2 + 1] << 8)
                    r = (v >> 11) << 3; g = ((v >> 5) & 63) << 2; b = (v & 31) << 3
                out += bytes((r, g, b))
        with open(path, 'wb') as f:
            f.write(b'P6 %d %d 255\n' % (w, h)); f.write(out)

    def play(self, movie, frames, shots=(), outdir='.', start=0):
        ev = parse_movie(movie) if isinstance(movie, str) else movie
        for fr in range(start, frames):
            m = 0
            for f0, mm in ev:
                if f0 <= fr: m = mm
                else: break
            self.held = m
            self.run(1)
            if fr in shots:
                self.screenshot(os.path.join(outdir, 'f%06d.ppm' % fr))

if __name__ == '__main__':
    rom, movie, frames, outdir = sys.argv[1:5]
    shots = [int(x) for x in sys.argv[5].split(',')] if len(sys.argv) > 5 else []
    e = Emu(rom); e.play(movie, int(frames), shots, outdir)
    e.screenshot(os.path.join(outdir, 'last.ppm'))
    open(os.path.join(outdir, 'wram.bin'), 'wb').write(e.wram())
