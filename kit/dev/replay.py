"""Boot a ROM from power-on to the Prologue player phase with a fixed input script,
then capture Sigurd's and Noish's status pages."""
import sys; sys.path.insert(0,'/home/claude/fe4/tools')
from nav import *
rom, tag = sys.argv[1], sys.argv[2]
e=Emu(rom); e.run(900)
for b in ['start','start']: hold(e,b)
for i in range(12): hold(e,'a',10,240)
for i in range(240): hold(e,'a',4,20)
hold(e,'start',4,120)
for i in range(700): hold(e,'a' if i%2 else 'b',3,12)
hold(e,'b',3,30)
open(f'/home/claude/fe4/state_map_{tag}.bin','wb').write(e.save_state())
s=e.save_state()
paths=[]
for k,seq in enumerate([['x'],['x','down'],['r','x'],['r','x','down']]):
    e.load_state(s)
    for b in seq: hold(e,b,4,90)
    p=f'/home/claude/fe4/shots/{tag}_{k}.png'; e.screenshot(p); paths.append(p)
grid(paths,f'/home/claude/fe4/shots/{tag}_status.png',2)
