"""Build movie files (lines "<frame> <buttons>") from a compact script.
Script ops (one per line):  wait N | press BTNS HOLD AFTER [xCOUNT]
"""
import sys

def build(script):
    ev = []; fr = 0
    for line in script.strip().splitlines():
        p = line.split()
        if not p or p[0].startswith('#'): continue
        if p[0] == 'wait':
            fr += int(p[1])
        elif p[0] == 'press':
            btns = p[1]; hold = int(p[2]); after = int(p[3])
            cnt = int(p[4][1:]) if len(p) > 4 else 1
            for _ in range(cnt):
                for b in btns.split('/'):
                    ev.append((fr, b)); fr += hold
                    ev.append((fr, '-')); fr += after
    return ev, fr

def write(ev, path):
    with open(path, 'w') as f:
        f.write('0 -\n')
        for fr, b in ev: f.write('%d %s\n' % (fr, b))

# power-on -> new game -> chapter 1 player phase (blank SRAM)
CH1 = """
wait 900
press S 5 90 x2
press A 10 240 x12
press A 4 20 x240
press S 4 120
press A/B 3 12 x350
press B 3 30
"""

if __name__ == '__main__':
    ev, n = build(CH1)
    write(ev, sys.argv[1]); print(n)
