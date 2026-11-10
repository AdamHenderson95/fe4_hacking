"""Minimal two-pass 65816 assembler (for small ROM hooks).
Syntax:  label:   OP operand   ; comment     .db 1,2  .dw $1234,label  .org $85FA00
Operands: #imm  $dp  $abs  $long  $dp,X  $abs,X  $abs,Y  $long,X  ($dp),Y  [$dp]  [$dp],Y  $sr,S  label
Immediate width follows REP/SEP seen so far (start state given by .m / .x directives).
"""
import os, re

OPTAB = os.path.join(os.path.dirname(__file__), '..', 'work', 'optab.txt')
TAB = {}
for line in open(OPTAB):
    c, op, mode = line.split()
    TAB.setdefault(op, {})[mode] = int(c, 16)

ALIAS = {'asl': ('asla', 'imp'), 'lsr': ('lsra', 'imp'), 'rol': ('rola', 'imp'), 'ror': ('rora', 'imp'),
         'inc': ('inca', 'imp'), 'dec': ('deca', 'imp')}

def num(s, labels):
    s = s.strip()
    if s.startswith('$'): return int(s[1:], 16)
    if s.startswith('%'): return int(s[1:], 2)
    if re.fullmatch(r'-?\d+', s): return int(s)
    if s in labels: return labels[s]
    m = re.fullmatch(r'(\w+)\s*([+-])\s*(.+)', s)
    if m and m.group(1) in labels:
        v = num(m.group(3), labels)
        return labels[m.group(1)] + (v if m.group(2) == '+' else -v)
    raise KeyError(s)

def assemble(src, org):
    labels = {}
    for pass_ in (0, 1):
        pc = org; out = bytearray(); mflag = 0; xflag = 0
        for raw in src.splitlines():
            line = raw.split(';')[0].strip()
            if not line: continue
            while True:
                m = re.match(r'^(\w+):\s*(.*)$', line)
                if not m: break
                labels[m.group(1)] = pc
                line = m.group(2).strip()
            if not line: continue
            parts = line.split(None, 1)
            op = parts[0].lower(); arg = parts[1].strip() if len(parts) > 1 else ''
            def emit(*bs):
                nonlocal pc
                out.extend(b & 0xff for b in bs); pc += len(bs)
            def val(s):
                try: return num(s, labels)
                except KeyError:
                    if pass_ == 0: return 0
                    raise
            if op == '.m': mflag = int(arg); continue
            if op == '.x': xflag = int(arg); continue
            if op == '.db':
                for a in arg.split(','): emit(val(a))
                continue
            if op == '.dw':
                for a in arg.split(','): v = val(a); emit(v, v >> 8)
                continue
            if op in ALIAS and arg in ('', 'A', 'a'):
                op, mode = ALIAS[op]; emit(TAB[op][mode]); continue
            ops = TAB[op]
            if not arg:
                emit(ops['imp']); continue
            if arg.startswith('#'):
                v = val(arg[1:])
                if 'imm(s)' in ops:
                    emit(ops['imm(s)'], v)
                    if op == 'rep':
                        if v & 0x20: mflag = 0
                        if v & 0x10: xflag = 0
                    if op == 'sep':
                        if v & 0x20: mflag = 1
                        if v & 0x10: xflag = 1
                    continue
                if 'imm(m)' in ops:
                    if mflag: emit(ops['imm(m)'], v)
                    else: emit(ops['imm(m)'], v, v >> 8)
                    continue
                if 'imm(x)' in ops:
                    if xflag: emit(ops['imm(x)'], v)
                    else: emit(ops['imm(x)'], v, v >> 8)
                    continue
                raise ValueError(line)
            if 'rel' in ops:
                t = val(arg); d = t - (pc + 2)
                if pass_ and not -128 <= d <= 127: raise ValueError('branch out of range: ' + line)
                emit(ops['rel'], d); continue
            if op == 'brl':
                t = val(arg); d = t - (pc + 3); emit(ops['rll'], d, d >> 8); continue
            if op in ('jsl', 'jml') and not arg.startswith('['):
                v = val(arg); emit(ops['abl'], v, v >> 8, v >> 16); continue
            if op in ('jsr', 'jmp') and not arg.startswith('('):
                v = val(arg); emit(ops['abs'], v, v >> 8); continue
            m = re.fullmatch(r'\[(.+)\],\s*[Yy]', arg)
            if m: emit(ops['ily'], val(m.group(1))); continue
            m = re.fullmatch(r'\[(.+)\]', arg)
            if m: emit(ops['idl'], val(m.group(1))); continue
            m = re.fullmatch(r'\((.+)\),\s*[Yy]', arg)
            if m: emit(ops.get('idy(r)', ops.get('idy')), val(m.group(1))); continue
            m = re.fullmatch(r'(.+),\s*[Ss]', arg)
            if m: emit(ops['sr'], val(m.group(1))); continue
            m = re.fullmatch(r'(.+),\s*([XxYy])', arg)
            base, idx = (m.group(1), m.group(2).lower()) if m else (arg, None)
            v = val(base)
            digits = len(base[1:]) if base.startswith('$') else (6 if v > 0xffff else 4)
            if digits <= 2 and idx in (None, 'x', 'y') and ('dp' + (idx or '')) in ops:
                emit(ops['dp' + (idx or '')], v); continue
            if digits >= 6 or v > 0xffff:
                emit(ops['alx' if idx == 'x' else 'abl'], v, v >> 8, v >> 16); continue
            key = 'abs' if idx is None else ('ab' + idx)
            code = ops.get(key, ops.get(key + '(r)'))
            emit(code, v, v >> 8)
        if pass_ == 1: return bytes(out), labels

def snes_to_file(adr):
    bank = adr >> 16; a = adr & 0xffff
    return (((bank & 0x3f) << 16) | (0 if bank >= 0x80 else 0x400000) | a)
