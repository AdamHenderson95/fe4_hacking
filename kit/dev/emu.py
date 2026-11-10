"""Headless SNES harness over the Snes9x libretro core (ctypes).

Usage:
    from emu import Emu
    e = Emu('rom.sfc')
    e.run(600)                       # frames
    e.press('start', 2); e.run(60)   # hold a button N frames
    e.screenshot('shot.png')
    wram = e.wram()                  # bytes, 128 KiB
"""
import ctypes as C
import os

CORE = '/usr/lib/x86_64-linux-gnu/libretro/snes9x_libretro.so'

BTN = {'b': 0, 'y': 1, 'select': 2, 'start': 3, 'up': 4, 'down': 5, 'left': 6,
       'right': 7, 'a': 8, 'x': 9, 'l': 10, 'r': 11}

ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_SAVE_DIRECTORY = 31
ENV_GET_LOG_INTERFACE = 27
ENV_GET_CAN_DUPE = 3


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Emu:
    def __init__(self, rom_path, core=CORE):
        self.lib = C.CDLL(core)
        self.held = set()
        self.frame = None
        self.fmt = 0  # 0=0RGB1555, 1=XRGB8888, 2=RGB565
        self._sysdir = C.c_char_p(os.path.abspath(os.path.dirname(rom_path)).encode())
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(lambda l, r: None),
                     AUDIO_BATCH_CB(lambda d, n: n), POLL_CB(lambda: None), STATE_CB(self._state)]
        L = self.lib
        L.retro_set_environment(self._cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self._cbs[1])
        L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3])
        L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        self._rom = open(rom_path, 'rb').read()
        if len(self._rom) % 0x8000 == 512:  # strip copier header
            self._rom = self._rom[512:]
        self._buf = C.create_string_buffer(self._rom, len(self._rom))
        gi = GameInfo(rom_path.encode(), C.cast(self._buf, C.c_void_p), len(self._rom), None)
        if not L.retro_load_game(C.byref(gi)):
            raise RuntimeError('retro_load_game failed')
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_serialize.restype = C.c_bool
        L.retro_unserialize.restype = C.c_bool

    # --- callbacks
    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._sysdir.value
            return True
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        return False

    def _video(self, data, w, h, pitch):
        if data:
            self.frame = (C.string_at(data, pitch * h), w, h, pitch)

    def _state(self, port, device, index, id_):
        if port == 0 and device == 1 and id_ in self.held:
            return 1
        return 0

    # --- control
    def run(self, n=1):
        for _ in range(n):
            self.lib.retro_run()

    def press(self, buttons, frames=2, release=8):
        if isinstance(buttons, str):
            buttons = [buttons]
        self.held = {BTN[b] for b in buttons}
        self.run(frames)
        self.held = set()
        self.run(release)

    def wram(self):
        p = self.lib.retro_get_memory_data(2)
        n = self.lib.retro_get_memory_size(2)
        return C.string_at(p, n)

    def poke(self, addr, data):
        """write bytes into WRAM ($7E:0000 + addr)"""
        p = self.lib.retro_get_memory_data(2)
        C.memmove(p + addr, bytes(data), len(data))

    def sram(self):
        p = self.lib.retro_get_memory_data(0)
        n = self.lib.retro_get_memory_size(0)
        return C.string_at(p, n) if p else b''

    def save_state(self):
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        assert self.lib.retro_serialize(buf, n)
        return buf.raw

    def load_state(self, raw):
        buf = C.create_string_buffer(raw, len(raw))
        assert self.lib.retro_unserialize(buf, len(raw))

    def screenshot(self, path):
        from PIL import Image
        data, w, h, pitch = self.frame
        img = Image.new('RGB', (w, h))
        px = img.load()
        bpp = 4 if self.fmt == 1 else 2
        for y in range(h):
            row = data[y * pitch:y * pitch + w * bpp]
            for x in range(w):
                if bpp == 4:
                    v = int.from_bytes(row[x * 4:x * 4 + 4], 'little')
                    px[x, y] = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                else:
                    v = row[x * 2] | row[x * 2 + 1] << 8
                    if self.fmt == 2:
                        px[x, y] = ((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3)
                    else:
                        px[x, y] = (((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3)
        img.save(path)
