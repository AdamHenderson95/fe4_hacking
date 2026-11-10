// FE4 65816 -> C static recompiler.
//
// Each block starts at a known (address, e/m/x flag state) and runs to the next control-flow
// instruction. The emitted C performs exactly the bus reads/writes, idle cycles and interrupt
// polls that LakeSnes's interpreter (snes/cpu.c) performs, so a recompiled run can be checked
// against the interpreter instruction by instruction. Operand bytes, addressing math with
// constants, and register widths are resolved at translation time.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#include "recomp.h"
#include "rc_ops.h"

typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;

static const u8* ROM; static int ROMSIZE;
static FILE* OUT;

static int is_rom(u32 adr) {
  u8 bank = adr >> 16;
  if(bank == 0x7e || bank == 0x7f) return 0;
  if((bank & 0x7f) >= 0x40) return 1;
  return (adr & 0xffff) >= 0x8000;
}
// ExHiROM mapping, same as cart_readExHirom
static u8 rom8(u32 adr) {
  u8 bank = adr >> 16; u16 a = adr & 0xffff;
  int second = bank < 0x80; bank &= 0x7f;
  return ROM[((((u32)bank & 0x3f) << 16) | (second ? 0x400000 : 0) | a) & (ROMSIZE - 1)];
}

// ---------- worklist / visited ----------
typedef struct { u32 pc; u8 fs; } Ent;
static Ent* work; static int nwork, capwork;
static u32* seenK; static u32 seenMask; static int seenN;
static Ent* done; static int ndone, capdone;

static u32 hsh(u32 k) { k *= 0x9E3779B1u; return k ^ (k >> 15); }
static int seen_add(u32 pc, int fs) {
  u32 key = (pc << 3) | fs | 0x80000000u;
  if((u32)seenN * 2 >= seenMask) {
    u32 om = seenMask; u32* ok = seenK;
    seenMask = om ? om * 2 + 1 : 0xffff; seenK = calloc(seenMask + 1, 4); seenN = 0;
    for(u32 i = 0; ok && i <= om; i++) if(ok[i]) { u32 h = hsh(ok[i]) & seenMask; while(seenK[h]) h = (h + 1) & seenMask; seenK[h] = ok[i]; seenN++; }
    free(ok);
  }
  u32 h = hsh(key) & seenMask;
  while(seenK[h]) { if(seenK[h] == key) return 0; h = (h + 1) & seenMask; }
  seenK[h] = key; seenN++;
  return 1;
}
static int g_follow = 1;
static void push_ent(u32 pc, int fs) {
  if(!is_rom(pc)) return;
  if(!seen_add(pc, fs)) return;
  if(nwork == capwork) { capwork = capwork ? capwork * 2 : 4096; work = realloc(work, capwork * sizeof(Ent)); }
  work[nwork].pc = pc; work[nwork].fs = fs; nwork++;
}
static void succ(u32 pc, int fs) { if(g_follow) push_ent(pc, fs); }

// ---------- emit helpers ----------
static void E(const char* fmt, ...) { va_list ap; va_start(ap, fmt); fputs("  ", OUT); vfprintf(OUT, fmt, ap); va_end(ap); fputc('\n', OUT); }

static const char* reg_name_for(int op) {
  switch(op) { case O_CPX: case O_LDX: case O_STX: return "x"; case O_CPY: case O_LDY: case O_STY: return "y"; }
  return "a";
}

// compute part of read-type ops, value in variable v
static void emit_read_op(int op, int w8) {
  switch(op) {
    case O_ORA: if(w8) E("c->a = (c->a & 0xff00) | ((c->a | v) & 0xff); ZN8(c->a);"); else E("c->a |= v; ZN16(c->a);"); break;
    case O_AND: if(w8) E("c->a = (c->a & 0xff00) | ((c->a & v) & 0xff); ZN8(c->a);"); else E("c->a &= v; ZN16(c->a);"); break;
    case O_EOR: if(w8) E("c->a = (c->a & 0xff00) | ((c->a ^ v) & 0xff); ZN8(c->a);"); else E("c->a ^= v; ZN16(c->a);"); break;
    case O_ADC: E(w8 ? "rcADC8(c, v);" : "rcADC16(c, v);"); break;
    case O_SBC: E(w8 ? "rcSBC8(c, v);" : "rcSBC16(c, v);"); break;
    case O_CMP: case O_CPX: case O_CPY: {
      const char* r = reg_name_for(op);
      if(w8) E("{ int t = (c->%s & 0xff) + (v ^ 0xff) + 1; c->c = t > 0xff; ZN8(t); }", r);
      else E("{ int t = c->%s + (v ^ 0xffff) + 1; c->c = t > 0xffff; ZN16(t); }", r);
      break;
    }
    case O_BIT:
      if(w8) E("c->z = ((c->a & 0xff) & v) == 0; c->n = (v & 0x80) != 0; c->v = (v & 0x40) != 0;");
      else E("c->z = (c->a & v) == 0; c->n = (v & 0x8000) != 0; c->v = (v & 0x4000) != 0;");
      break;
    case O_LDA: if(w8) E("c->a = (c->a & 0xff00) | v; ZN8(c->a);"); else E("c->a = v; ZN16(c->a);"); break;
    case O_LDX: E("c->x = v; %s", w8 ? "ZN8(c->x);" : "ZN16(c->x);"); break;
    case O_LDY: E("c->y = v; %s", w8 ? "ZN8(c->y);" : "ZN16(c->y);"); break;
  }
}

static int op_kind(int op) {
  switch(op) {
    case O_ORA: case O_AND: case O_EOR: case O_ADC: case O_SBC: case O_CMP: case O_BIT: case O_LDA: return 1; // read, m
    case O_CPX: case O_CPY: case O_LDX: case O_LDY: return 2; // read, x
    case O_STA: case O_STZ: return 3; // store, m
    case O_STX: case O_STY: return 4; // store, x
    case O_ASL: case O_LSR: case O_ROL: case O_ROR: case O_INC: case O_DEC: case O_TSB: case O_TRB: return 5; // rmw, m
  }
  return 0;
}

static void emit_rmw(int op, int w8) {
  if(w8) {
    E("{ u8 v = rcR(c, lo); rcI(c);");
    switch(op) {
      case O_ASL: E("  int r = v << 1; c->c = (r & 0x100) != 0; rcCI(c); rcW(c, lo, r); ZN8(r); }"); break;
      case O_ROL: E("  int r = (v << 1) | c->c; c->c = (r & 0x100) != 0; rcCI(c); rcW(c, lo, r); ZN8(r); }"); break;
      case O_LSR: E("  int r = v >> 1; c->c = v & 1; rcCI(c); rcW(c, lo, r); ZN8(r); }"); break;
      case O_ROR: E("  int r = (v >> 1) | (c->c << 7); rcCI(c); rcW(c, lo, r); ZN8(r); c->c = v & 1; }"); break;
      case O_INC: E("  int r = v + 1; rcCI(c); rcW(c, lo, r); ZN8(r); }"); break;
      case O_DEC: E("  int r = v - 1; rcCI(c); rcW(c, lo, r); ZN8(r); }"); break;
      case O_TSB: E("  c->z = ((c->a & 0xff) & v) == 0; rcCI(c); rcW(c, lo, v | (c->a & 0xff)); }"); break;
      case O_TRB: E("  c->z = ((c->a & 0xff) & v) == 0; rcCI(c); rcW(c, lo, v & ~(c->a & 0xff)); }"); break;
    }
  } else {
    E("{ u16 v = rcRW(c, lo, hi, 0); rcI(c);");
    switch(op) {
      case O_ASL: E("  int r = v << 1; c->c = (r & 0x10000) != 0; rcWW(c, lo, hi, r, 1, 1); ZN16(r); }"); break;
      case O_ROL: E("  int r = (v << 1) | c->c; c->c = (r & 0x10000) != 0; rcWW(c, lo, hi, r, 1, 1); ZN16(r); }"); break;
      case O_LSR: E("  int r = v >> 1; c->c = v & 1; rcWW(c, lo, hi, r, 1, 1); ZN16(r); }"); break;
      case O_ROR: E("  int r = (v >> 1) | (c->c << 15); rcWW(c, lo, hi, r, 1, 1); ZN16(r); c->c = v & 1; }"); break;
      case O_INC: E("  int r = v + 1; rcWW(c, lo, hi, r, 1, 1); ZN16(r); }"); break;
      case O_DEC: E("  int r = v - 1; rcWW(c, lo, hi, r, 1, 1); ZN16(r); }"); break;
      case O_TSB: E("  c->z = (c->a & v) == 0; rcWW(c, lo, hi, v | c->a, 1, 1); }"); break;
      case O_TRB: E("  c->z = (c->a & v) == 0; rcWW(c, lo, hi, v & ~c->a, 1, 1); }"); break;
    }
  }
}

// operand fetches + effective address (lo/hi). b[] = operand bytes, A[] = their addresses
static void emit_addr(int mode, const u8* b, const u32* A, int xflag) {
  u32 o16 = b[0] | (b[1] << 8), o24 = o16 | ((u32)b[2] << 16);
  switch(mode) {
    case M_DP: E("rcF(c, 0x%06X, 0x%02X); DPX;", A[0], b[0]);
      E("u32 lo = (c->dp + 0x%02X) & 0xffff, hi = (c->dp + 0x%02X) & 0xffff;", b[0], b[0] + 1); break;
    case M_DPX: case M_DPY: { const char* r = mode == M_DPX ? "x" : "y";
      E("rcF(c, 0x%06X, 0x%02X); DPX; rcI(c);", A[0], b[0]);
      E("u32 lo = (c->dp + 0x%02X + c->%s) & 0xffff, hi = (c->dp + 0x%02X + c->%s) & 0xffff;", b[0], r, b[0] + 1, r); break; }
    case M_IDP: E("rcF(c, 0x%06X, 0x%02X); DPX;", A[0], b[0]);
      E("u16 p = rcRW(c, (c->dp + 0x%02X) & 0xffff, (c->dp + 0x%02X) & 0xffff, 0);", b[0], b[0] + 1);
      E("u32 lo = DB + p, hi = (DB + p + 1) & 0xffffff;"); break;
    case M_IDX: E("rcF(c, 0x%06X, 0x%02X); DPX; rcI(c);", A[0], b[0]);
      E("u16 p = rcRW(c, (c->dp + 0x%02X + c->x) & 0xffff, (c->dp + 0x%02X + c->x) & 0xffff, 0);", b[0], b[0] + 1);
      E("u32 lo = DB + p, hi = (DB + p + 1) & 0xffffff;"); break;
    case M_IDY: case M_IDY_W: E("rcF(c, 0x%06X, 0x%02X); DPX;", A[0], b[0]);
      E("u16 p = rcRW(c, (c->dp + 0x%02X) & 0xffff, (c->dp + 0x%02X) & 0xffff, 0);", b[0], b[0] + 1);
      if(mode == M_IDY_W || !xflag) E("rcI(c);"); else E("if((p >> 8) != ((p + c->y) >> 8)) rcI(c);");
      E("u32 lo = (DB + p + c->y) & 0xffffff, hi = (DB + p + c->y + 1) & 0xffffff;"); break;
    case M_IDL: case M_ILY: E("rcF(c, 0x%06X, 0x%02X); DPX;", A[0], b[0]);
      E("u32 p = rcRW(c, (c->dp + 0x%02X) & 0xffff, (c->dp + 0x%02X) & 0xffff, 0);", b[0], b[0] + 1);
      E("p |= rcR(c, (c->dp + 0x%02X) & 0xffff) << 16;", b[0] + 2);
      if(mode == M_IDL) E("u32 lo = p, hi = (p + 1) & 0xffffff;");
      else E("u32 lo = (p + c->y) & 0xffffff, hi = (p + c->y + 1) & 0xffffff;");
      break;
    case M_SR: E("rcF(c, 0x%06X, 0x%02X); rcI(c);", A[0], b[0]);
      E("u32 lo = (c->sp + 0x%02X) & 0xffff, hi = (c->sp + 0x%02X) & 0xffff;", b[0], b[0] + 1); break;
    case M_ISY: E("rcF(c, 0x%06X, 0x%02X); rcI(c);", A[0], b[0]);
      E("u16 p = rcRW(c, (c->sp + 0x%02X) & 0xffff, (c->sp + 0x%02X) & 0xffff, 0); rcI(c);", b[0], b[0] + 1);
      E("u32 lo = (DB + p + c->y) & 0xffffff, hi = (DB + p + c->y + 1) & 0xffffff;"); break;
    case M_ABS: E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X);", A[0], b[0], A[1], b[1]);
      E("u32 lo = DB + 0x%04X, hi = (DB + 0x%04X) & 0xffffff;", o16, o16 + 1); break;
    case M_ABX: case M_ABX_W: case M_ABY: case M_ABY_W: {
      const char* r = (mode == M_ABX || mode == M_ABX_W) ? "x" : "y";
      int w = mode == M_ABX_W || mode == M_ABY_W;
      E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X);", A[0], b[0], A[1], b[1]);
      if(w || !xflag) E("rcI(c);"); else E("if((0x%04X >> 8) != ((0x%04X + c->%s) >> 8)) rcI(c);", o16, o16, r);
      E("u32 lo = (DB + 0x%04X + c->%s) & 0xffffff, hi = (DB + 0x%04X + c->%s) & 0xffffff;", o16, r, o16 + 1, r); break; }
    case M_ABL: E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X);", A[0], b[0], A[1], b[1], A[2], b[2]);
      E("u32 lo = 0x%06X, hi = 0x%06X;", o24, (o24 + 1) & 0xffffff); break;
    case M_ALX: E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X);", A[0], b[0], A[1], b[1], A[2], b[2]);
      E("u32 lo = (0x%06X + c->x) & 0xffffff, hi = (0x%06X + c->x + 1) & 0xffffff;", o24, o24); break;
    default: E("#error bad mode %d", mode);
  }
}

// ---------- disassembly for comments ----------
static void disasm(char* s, u8 opc, const u8* b, int len, u32 pc24) {
  int op = rc_opTab[opc][0], mode = rc_opTab[opc][1];
  char mn[8]; strcpy(mn, rc_opNames[op]);
  if(mn[3] == 'a' && (op == O_ASLA || op == O_LSRA || op == O_ROLA || op == O_RORA || op == O_INCA || op == O_DECA)) mn[3] = 0;
  if(op == O_BITI) strcpy(mn, "bit");
  for(char* p = mn; *p; p++) *p -= 32;
  u32 o16 = b[0] | (b[1] << 8), o24 = o16 | (b[2] << 16);
  switch(mode) {
    case M_IMP: sprintf(s, "%s%s", mn, (op == O_ASLA || op == O_LSRA || op == O_ROLA || op == O_RORA || op == O_INCA || op == O_DECA) ? " A" : ""); break;
    case M_IMM_M: case M_IMM_X: if(len == 2) sprintf(s, "%s #$%02X", mn, b[0]); else sprintf(s, "%s #$%04X", mn, o16); break;
    case M_IMM8: sprintf(s, "%s #$%02X", mn, b[0]); break;
    case M_IMM16: sprintf(s, "%s $%04X", mn, o16); break;
    case M_DP: sprintf(s, "%s $%02X", mn, b[0]); break;
    case M_DPX: sprintf(s, "%s $%02X,X", mn, b[0]); break;
    case M_DPY: sprintf(s, "%s $%02X,Y", mn, b[0]); break;
    case M_IDP: sprintf(s, "%s ($%02X)", mn, b[0]); break;
    case M_IDX: sprintf(s, "%s ($%02X,X)", mn, b[0]); break;
    case M_IDY: case M_IDY_W: sprintf(s, "%s ($%02X),Y", mn, b[0]); break;
    case M_IDL: sprintf(s, "%s [$%02X]", mn, b[0]); break;
    case M_ILY: sprintf(s, "%s [$%02X],Y", mn, b[0]); break;
    case M_SR: sprintf(s, "%s $%02X,S", mn, b[0]); break;
    case M_ISY: sprintf(s, "%s ($%02X,S),Y", mn, b[0]); break;
    case M_ABS: sprintf(s, "%s $%04X", mn, o16); break;
    case M_ABX: case M_ABX_W: sprintf(s, "%s $%04X,X", mn, o16); break;
    case M_ABY: case M_ABY_W: sprintf(s, "%s $%04X,Y", mn, o16); break;
    case M_ABL: sprintf(s, "%s $%06X", mn, o24); break;
    case M_ALX: sprintf(s, "%s $%06X,X", mn, o24); break;
    case M_IND: sprintf(s, "%s ($%04X)", mn, o16); break;
    case M_IAX: sprintf(s, "%s ($%04X,X)", mn, o16); break;
    case M_IAL: sprintf(s, "%s [$%04X]", mn, o16); break;
    case M_REL: sprintf(s, "%s $%04X", mn, (u16)((pc24 & 0xffff) + 2 + (int8_t)b[0])); break;
    case M_RLL: sprintf(s, "%s $%04X", mn, (u16)((pc24 & 0xffff) + 3 + (int16_t)o16)); break;
    case M_BM: sprintf(s, "%s $%02X,$%02X", mn, b[1], b[0]); break;
    default: sprintf(s, "%s ?", mn);
  }
}

// ---------- block emission ----------
#define MAXI 200
static RcGenStats st;

static void emit_block(u32 pc24, int fs) {
  u32 bank = pc24 & 0xff0000; u16 pc = pc24 & 0xffff;
  int e = fs == 4, m = e ? 1 : (fs >> 1) & 1, x = e ? 1 : fs & 1;
  fprintf(OUT, "static void B_%06X_%d(RcCpu* c) {\n", pc24, fs);
  st.blocks++;
  for(int n = 0; n < MAXI; n++) {
    u32 A0 = bank | pc;
    if(!is_rom(A0)) break;
    u8 opc = rom8(A0);
    int len = rc_opLen(opc, m, x);
    if((u32)pc + len > 0x10000) break; // don't cross a bank boundary mid-instruction
    u8 b[3]; u32 A[3];
    for(int i = 0; i < 3; i++) { A[i] = bank | ((pc + 1 + i) & 0xffff); b[i] = rom8(A[i]); }
    u16 npc = pc + len;
    u32 N24 = bank | npc;
    int op = rc_opTab[opc][0], mode = rc_opTab[opc][1];
    char dis[64]; disasm(dis, opc, b, len, A0);
    fprintf(OUT, "  // %02X:%04X  %-16s", bank >> 16, pc, dis);
    for(int i = 0; i < len; i++) fprintf(OUT, " %02X", i ? b[i - 1] : opc);
    fprintf(OUT, "\n");
    st.instrs++;
    E("rcF(c, 0x%06X, 0x%02X);", A0, opc);
    int kind = op_kind(op);
    int term = rc_opEndsBlock(opc);
    if(kind && mode != M_IMM_M && mode != M_IMM_X) {
      int w8 = (kind == 2 || kind == 4) ? x : m;
      E("{");
      emit_addr(mode, b, A, x);
      if(kind == 1 || kind == 2) {
        if(w8) E("rcCI(c); u8 v = rcR(c, lo);"); else E("u16 v = rcRW(c, lo, hi, 1);");
        emit_read_op(op, w8);
      } else if(kind == 3 || kind == 4) {
        const char* val = op == O_STZ ? "0" : op == O_STX ? "c->x" : op == O_STY ? "c->y" : "c->a";
        if(w8) E("rcCI(c); rcW(c, lo, %s);", val); else E("rcWW(c, lo, hi, %s, 0, 1);", val);
      } else {
        emit_rmw(op, w8);
      }
      E("}");
    } else if(kind == 1 || kind == 2) { // immediate
      int w8 = kind == 2 ? x : m;
      E("{");
      if(w8) E("rcCI(c); rcF(c, 0x%06X, 0x%02X); u8 v = 0x%02X;", A[0], b[0], b[0]);
      else E("rcF(c, 0x%06X, 0x%02X); rcCI(c); rcF(c, 0x%06X, 0x%02X); u16 v = 0x%04X;", A[0], b[0], A[1], b[1], b[0] | (b[1] << 8));
      emit_read_op(op, w8);
      E("}");
    } else switch(opc) {
      // ----- control flow (block terminators) -----
      case 0x10: case 0x30: case 0x50: case 0x70: case 0x90: case 0xb0: case 0xd0: case 0xf0: {
        static const char* cond[8] = { "!c->n", "c->n", "!c->v", "c->v", "!c->c", "c->c", "!c->z", "c->z" };
        u16 t = npc + (int8_t)b[0];
        E("if(%s) { rcF(c, 0x%06X, 0x%02X); rcCI(c); rcI(c); c->pc = 0x%04X; }", cond[opc >> 5], A[0], b[0], t);
        E("else { rcCI(c); rcF(c, 0x%06X, 0x%02X); c->pc = 0x%04X; }", A[0], b[0], npc);
        succ(bank | t, fs); succ(N24, fs);
        break;
      }
      case 0x80: { u16 t = npc + (int8_t)b[0];
        E("rcF(c, 0x%06X, 0x%02X); rcCI(c); rcI(c); c->pc = 0x%04X;", A[0], b[0], t); succ(bank | t, fs); break; }
      case 0x82: { u16 t = npc + (int16_t)(b[0] | (b[1] << 8));
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcCI(c); rcI(c); c->pc = 0x%04X;", A[0], b[0], A[1], b[1], t); succ(bank | t, fs); break; }
      case 0x4c: { u16 t = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcCI(c); rcF(c, 0x%06X, 0x%02X); c->pc = 0x%04X;", A[0], b[0], A[1], b[1], t); succ(bank | t, fs); break; }
      case 0x5c: { u16 t = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcCI(c); rcF(c, 0x%06X, 0x%02X); c->k = 0x%02X; c->pc = 0x%04X;", A[0], b[0], A[1], b[1], A[2], b[2], b[2], t);
        succ(((u32)b[2] << 16) | t, fs); break; }
      case 0x20: { u16 t = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcI(c); rcP16(c, 0x%04X, 1); c->pc = 0x%04X;", A[0], b[0], A[1], b[1], (u16)(npc - 1), t);
        succ(bank | t, fs); break; }
      case 0x22: { u16 t = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcP8(c, 0x%02X); rcI(c); rcF(c, 0x%06X, 0x%02X);", A[0], b[0], A[1], b[1], bank >> 16, A[2], b[2]);
        E("rcP16(c, 0x%04X, 1); c->pc = 0x%04X; c->k = 0x%02X;", (u16)(npc - 1), t, b[2]);
        succ(((u32)b[2] << 16) | t, fs); break; }
      case 0xfc: { u16 adr = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcP16(c, 0x%04X, 0); rcF(c, 0x%06X, 0x%02X); rcI(c);", A[0], b[0], (u16)(pc + 2), A[1], b[1]);
        E("c->pc = rcRW(c, 0x%06X | ((0x%04X + c->x) & 0xffff), 0x%06X | ((0x%04X + c->x + 1) & 0xffff), 1);", bank, adr, bank, adr);
        break; }
      case 0x6c: { u16 adr = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); c->pc = rcRW(c, 0x%04X, 0x%04X, 1);", A[0], b[0], A[1], b[1], adr, (adr + 1) & 0xffff); break; }
      case 0x7c: { u16 adr = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcI(c);", A[0], b[0], A[1], b[1]);
        E("c->pc = rcRW(c, 0x%06X | ((0x%04X + c->x) & 0xffff), 0x%06X | ((0x%04X + c->x + 1) & 0xffff), 1);", bank, adr, bank, adr); break; }
      case 0xdc: { u16 adr = b[0] | (b[1] << 8);
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); c->pc = rcRW(c, 0x%04X, 0x%04X, 0); rcCI(c); c->k = rcR(c, 0x%04X);",
          A[0], b[0], A[1], b[1], adr, (adr + 1) & 0xffff, (adr + 2) & 0xffff); break; }
      case 0x60: E("rcI(c); rcI(c); c->pc = rcL16(c, 0) + 1; rcCI(c); rcI(c);"); break;
      case 0x6b: E("rcI(c); rcI(c); c->pc = rcL16(c, 0) + 1; rcCI(c); c->k = rcL8(c);"); break;
      case 0x40: E("rcI(c); rcI(c); rcSF(c, rcL8(c)); c->pc = rcL16(c, 0); rcCI(c); c->k = rcL8(c);"); break;
      case 0x00: case 0x02: {
        u32 vec = opc == 0 ? (e ? 0xfffe : 0xffe6) : (e ? 0xfff4 : 0xffe4);
        E("rcF(c, 0x%06X, 0x%02X);%s rcP16(c, 0x%04X, 0); rcP8(c, rcGF(c));", A[0], b[0], e ? "" : " rcP8(c, c->k);", npc);
        E("c->i = 1; c->d = 0; c->k = 0; c->pc = rcRW(c, 0x%04X, 0x%04X, 1);", vec, vec + 1); break; }
      case 0x28: E("rcI(c); rcI(c); rcCI(c); rcSF(c, rcL8(c)); c->pc = 0x%04X;", npc); break;
      case 0xfb: E("rcIMP(c, 0x%06X, 0x%02X); { _Bool t = c->c; c->c = c->e; c->e = t; } rcSF(c, rcGF(c)); c->pc = 0x%04X;", A[0], b[0], npc); break;
      case 0x44: case 0x54: {
        const char* d = opc == 0x54 ? "++" : "--";
        E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); c->db = 0x%02X;", A[0], b[0], A[1], b[1], b[0]);
        E("{ u8 t = rcR(c, 0x%06X | c->x); rcW(c, 0x%06X | c->y, t); }", (u32)b[1] << 16, (u32)b[0] << 16);
        E("c->a--; c->x%s; c->y%s; c->pc = c->a != 0xffff ? 0x%04X : 0x%04X;", d, d, pc, npc);
        if(x) E("c->x &= 0xff; c->y &= 0xff;");
        E("rcI(c); rcCI(c); rcI(c);");
        break; }
      case 0xcb: E("c->waiting = 1; rcI(c); rcI(c); c->pc = 0x%04X;", npc); break;
      case 0xdb: E("c->stopped = 1; rcI(c); rcI(c); c->pc = 0x%04X;", npc); break;
      // ----- straight-line specials -----
      case 0x08: E("rcI(c); rcCI(c); rcP8(c, rcGF(c));"); break;
      case 0x0b: E("rcI(c); rcP16(c, c->dp, 1);"); break;
      case 0x2b: E("rcI(c); rcI(c); c->dp = rcL16(c, 1); ZN16(c->dp);"); break;
      case 0x48: E(m ? "rcI(c); rcCI(c); rcP8(c, c->a);" : "rcI(c); rcP16(c, c->a, 1);"); break;
      case 0xda: E(x ? "rcI(c); rcCI(c); rcP8(c, c->x);" : "rcI(c); rcP16(c, c->x, 1);"); break;
      case 0x5a: E(x ? "rcI(c); rcCI(c); rcP8(c, c->y);" : "rcI(c); rcP16(c, c->y, 1);"); break;
      case 0x8b: E("rcI(c); rcCI(c); rcP8(c, c->db);"); break;
      case 0x4b: E("rcI(c); rcCI(c); rcP8(c, 0x%02X);", bank >> 16); break;
      case 0x68: E(m ? "rcI(c); rcI(c); rcCI(c); c->a = (c->a & 0xff00) | rcL8(c); ZN8(c->a);" : "rcI(c); rcI(c); c->a = rcL16(c, 1); ZN16(c->a);"); break;
      case 0xfa: E(x ? "rcI(c); rcI(c); rcCI(c); c->x = rcL8(c); ZN8(c->x);" : "rcI(c); rcI(c); c->x = rcL16(c, 1); ZN16(c->x);"); break;
      case 0x7a: E(x ? "rcI(c); rcI(c); rcCI(c); c->y = rcL8(c); ZN8(c->y);" : "rcI(c); rcI(c); c->y = rcL16(c, 1); ZN16(c->y);"); break;
      case 0xab: E("rcI(c); rcI(c); rcCI(c); c->db = rcL8(c); ZN8(c->db);"); break;
      case 0xf4: E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcP16(c, 0x%04X, 1);", A[0], b[0], A[1], b[1], b[0] | (b[1] << 8)); break;
      case 0x62: E("rcF(c, 0x%06X, 0x%02X); rcF(c, 0x%06X, 0x%02X); rcI(c); rcP16(c, 0x%04X, 1);", A[0], b[0], A[1], b[1], (u16)(npc + (int16_t)(b[0] | (b[1] << 8)))); break;
      case 0xd4: E("{"); emit_addr(M_DP, b, A, x); E("rcP16(c, rcRW(c, lo, hi, 0), 1); }"); break;
      case 0x89:
        if(m) E("rcCI(c); rcF(c, 0x%06X, 0x%02X); c->z = ((c->a & 0xff) & 0x%02X) == 0;", A[0], b[0], b[0]);
        else E("rcF(c, 0x%06X, 0x%02X); rcCI(c); rcF(c, 0x%06X, 0x%02X); c->z = (c->a & 0x%04X) == 0;", A[0], b[0], A[1], b[1], b[0] | (b[1] << 8));
        break;
      case 0xc2: case 0xe2: {
        E("rcF(c, 0x%06X, 0x%02X); rcCI(c); rcSF(c, rcGF(c) %s 0x%02X); rcI(c);", A[0], b[0], opc == 0xc2 ? "& ~" : "|", b[0]);
        if(!e) {
          if(opc == 0xc2) { if(b[0] & 0x20) m = 0; if(b[0] & 0x10) x = 0; }
          else { if(b[0] & 0x20) m = 1; if(b[0] & 0x10) x = 1; }
        }
        break; }
      case 0x42: E("rcCI(c); rcF(c, 0x%06X, 0x%02X);", A[0], b[0]); break;
      case 0xeb: E("{ u8 l = c->a & 0xff, h = c->a >> 8; c->a = (l << 8) | h; ZN8(h); } rcI(c); rcCI(c); rcI(c);"); break;
      default: {
        // 2-cycle implied ops
        E("rcIMP(c, 0x%06X, 0x%02X);", A[0], b[0]);
        switch(opc) {
          case 0x0a: E(m ? "c->c = (c->a & 0x80) != 0; c->a = (c->a & 0xff00) | ((c->a << 1) & 0xff); ZN8(c->a);" : "c->c = (c->a & 0x8000) != 0; c->a <<= 1; ZN16(c->a);"); break;
          case 0x2a: E(m ? "{ int r = (c->a << 1) | c->c; c->c = (r & 0x100) != 0; c->a = (c->a & 0xff00) | (r & 0xff); } ZN8(c->a);"
                         : "{ int r = (c->a << 1) | c->c; c->c = (r & 0x10000) != 0; c->a = r; } ZN16(c->a);"); break;
          case 0x4a: E(m ? "c->c = c->a & 1; c->a = (c->a & 0xff00) | ((c->a >> 1) & 0x7f); ZN8(c->a);" : "c->c = c->a & 1; c->a >>= 1; ZN16(c->a);"); break;
          case 0x6a: E(m ? "{ _Bool t = c->a & 1; c->a = (c->a & 0xff00) | ((c->a >> 1) & 0x7f) | (c->c << 7); c->c = t; } ZN8(c->a);"
                         : "{ _Bool t = c->a & 1; c->a = (c->a >> 1) | (c->c << 15); c->c = t; } ZN16(c->a);"); break;
          case 0x1a: E(m ? "c->a = (c->a & 0xff00) | ((c->a + 1) & 0xff); ZN8(c->a);" : "c->a++; ZN16(c->a);"); break;
          case 0x3a: E(m ? "c->a = (c->a & 0xff00) | ((c->a - 1) & 0xff); ZN8(c->a);" : "c->a--; ZN16(c->a);"); break;
          case 0xe8: E(x ? "c->x = (c->x + 1) & 0xff; ZN8(c->x);" : "c->x++; ZN16(c->x);"); break;
          case 0xc8: E(x ? "c->y = (c->y + 1) & 0xff; ZN8(c->y);" : "c->y++; ZN16(c->y);"); break;
          case 0xca: E(x ? "c->x = (c->x - 1) & 0xff; ZN8(c->x);" : "c->x--; ZN16(c->x);"); break;
          case 0x88: E(x ? "c->y = (c->y - 1) & 0xff; ZN8(c->y);" : "c->y--; ZN16(c->y);"); break;
          case 0xaa: E(x ? "c->x = c->a & 0xff; ZN8(c->x);" : "c->x = c->a; ZN16(c->x);"); break;
          case 0xa8: E(x ? "c->y = c->a & 0xff; ZN8(c->y);" : "c->y = c->a; ZN16(c->y);"); break;
          case 0x8a: E(m ? "c->a = (c->a & 0xff00) | (c->x & 0xff); ZN8(c->a);" : "c->a = c->x; ZN16(c->a);"); break;
          case 0x98: E(m ? "c->a = (c->a & 0xff00) | (c->y & 0xff); ZN8(c->a);" : "c->a = c->y; ZN16(c->a);"); break;
          case 0x9b: E(x ? "c->y = c->x & 0xff; ZN8(c->y);" : "c->y = c->x; ZN16(c->y);"); break;
          case 0xbb: E(x ? "c->x = c->y & 0xff; ZN8(c->x);" : "c->x = c->y; ZN16(c->x);"); break;
          case 0xba: E(x ? "c->x = c->sp & 0xff; ZN8(c->x);" : "c->x = c->sp; ZN16(c->x);"); break;
          case 0x9a: E(e ? "c->sp = (c->x & 0xff) | 0x100;" : "c->sp = c->x;"); break;
          case 0x1b: E(e ? "c->sp = (c->a & 0xff) | 0x100;" : "c->sp = c->a;"); break;
          case 0x3b: E("c->a = c->sp; ZN16(c->a);"); break;
          case 0x5b: E("c->dp = c->a; ZN16(c->dp);"); break;
          case 0x7b: E("c->a = c->dp; ZN16(c->a);"); break;
          case 0x18: E("c->c = 0;"); break;
          case 0x38: E("c->c = 1;"); break;
          case 0x58: E("c->i = 0;"); break;
          case 0x78: E("c->i = 1;"); break;
          case 0xd8: E("c->d = 0;"); break;
          case 0xf8: E("c->d = 1;"); break;
          case 0xb8: E("c->v = 0;"); break;
          case 0xea: break;
          default: E("#error unhandled opcode %02X", opc);
        }
      }
    }
    if(term) {
      E("c->icount++; return;");
      fprintf(OUT, "}\n\n");
      return;
    }
    pc = npc;
    E("NEXT(0x%04X)", pc);
  }
  E("c->pc = 0x%04X; return;", pc);
  fprintf(OUT, "}\n\n");
}

RcGenStats rc_generate(const uint8_t* rom, int romSize, const RcGenEntry* entries, int n, int follow, FILE* out) {
  ROM = rom; ROMSIZE = romSize; OUT = out; g_follow = follow;
  memset(&st, 0, sizeof st);
  nwork = 0; ndone = 0; free(seenK); seenK = NULL; seenMask = 0; seenN = 0;
  for(int i = 0; i < n; i++) push_ent(entries[i].pc, entries[i].fs);
  fprintf(out, "// FE4 recompiled code. Generated from your ROM by fe4port; not for distribution.\n");
  fprintf(out, "#ifndef RC_GEN_INLINE\n#include \"rc_gen.h\"\n#endif\n\n");
  for(int i = 0; i < nwork; i++) {
    Ent en = work[i];
    { // skip entries whose first instruction would cross a bank boundary (block could not make progress)
      int e = en.fs == 4, m = e ? 1 : (en.fs >> 1) & 1, x = e ? 1 : en.fs & 1;
      if((u32)(en.pc & 0xffff) + rc_opLen(rom8(en.pc), m, x) > 0x10000) continue;
    }
    if(ndone == capdone) { capdone = capdone ? capdone * 2 : 4096; done = realloc(done, capdone * sizeof(Ent)); }
    done[ndone++] = en;
    emit_block(en.pc, en.fs);
  }
  fprintf(out, "const RcEntry rc_blocks[] = {\n");
  for(int i = 0; i < ndone; i++) fprintf(out, "  { 0x%06X, %d, B_%06X_%d },\n", done[i].pc, done[i].fs, done[i].pc, done[i].fs);
  fprintf(out, "  { 0, 0, 0 }\n};\nconst int rc_blockCountGen = %d;\n", ndone);
  fprintf(out, "const int rc_layout[3] = { sizeof(RcCpu), (int)(long long)&((RcCpu*)0)->icount, (int)(long long)&((RcCpu*)0)->brk };\n");
  return st;
}

#ifdef RECOMP_MAIN
// recomp rom.sfc entries.txt out.c [--nofollow]
int main(int argc, char** argv) {
  if(argc < 4) { fprintf(stderr, "usage: recomp rom.sfc entries.txt out.c [--nofollow] [--mincount N]\n"); return 1; }
  FILE* f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); int len = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t* rom = malloc(len); fread(rom, 1, len, f); fclose(f);
  if(len & 0x200) { memmove(rom, rom + 0x200, len - 0x200); len -= 0x200; }
  int follow = 1, mincount = 0;
  for(int i = 4; i < argc; i++) { if(!strcmp(argv[i], "--nofollow")) follow = 0; else if(!strcmp(argv[i], "--mincount")) mincount = atoi(argv[++i]); }
  RcGenEntry* ents = NULL; int n = 0, cap = 0;
  f = fopen(argv[2], "r");
  char line[128];
  while(f && fgets(line, sizeof line, f)) {
    unsigned pc, fs, cnt = 1;
    if(sscanf(line, "%x %u %u", &pc, &fs, &cnt) >= 2) {
      if((int)cnt < mincount) continue;
      if(n == cap) { cap = cap ? cap * 2 : 1024; ents = realloc(ents, cap * sizeof *ents); }
      ents[n].pc = pc; ents[n].fs = fs; n++;
    }
  }
  if(f) fclose(f);
  FILE* out = fopen(argv[3], "w");
  RcGenStats s = rc_generate(rom, len, ents, n, follow, out);
  fclose(out);
  fprintf(stderr, "entries=%d blocks=%d instrs=%d\n", n, s.blocks, s.instrs);
  return 0;
}
#endif
