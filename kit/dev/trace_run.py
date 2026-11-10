import sys, ctypes as C, numpy as np
sys.path.insert(0,'/home/claude/fe4/tools')
import emu
from nav import hold
CORE='/home/claude/fe4/core/snes9x_trace_libretro.so'
e=emu.Emu('/home/claude/fe4/rom_orig.smc', core=CORE)
L=e.lib
L.fe4_trace_rom_reader.restype=C.POINTER(C.c_uint32)
L.fe4_trace_rom_exec.restype=C.POINTER(C.c_uint8)
L.fe4_trace_ram_writer.restype=C.POINTER(C.c_uint32)
L.fe4_trace_clear(); L.fe4_trace_enable(1)
e.run(900)
for b in ['start','start']: hold(e,b)
for i in range(12): hold(e,'a',10,240)
for i in range(240): hold(e,'a',4,20)
hold(e,'start',4,120)
for i in range(700): hold(e,'a' if i%2 else 'b',3,12)
hold(e,'b',3,30)
L.fe4_trace_enable(0)
rr=np.ctypeslib.as_array(L.fe4_trace_rom_reader(),(0x800000,)).copy()
ex=np.ctypeslib.as_array(L.fe4_trace_rom_exec(),(0x800000,)).copy()
rw=np.ctypeslib.as_array(L.fe4_trace_ram_writer(),(0x20000,)).copy()
np.savez_compressed('/home/claude/fe4/trace_prologue.npz', rr=rr, ex=ex, rw=rw)
open('/home/claude/fe4/state_map_tr.bin','wb').write(e.save_state())
w=e.wram()
print('unit ptr check', w[0x2672:0x2676].hex())
e.screenshot('/home/claude/fe4/shots/trace_end.png')
