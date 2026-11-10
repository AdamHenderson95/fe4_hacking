// Runtime for recompiled code: bus helpers that mirror the LakeSnes interpreter
// cycle for cycle, the block table, and the dispatcher.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "snes.h"
#include "cpu.h"
#include "dma.h"
#include "rc_rt.h"
#include "rc_ops.h"

// ---- layout check between Cpu and RcCpu ----
#define SAME(f) _Static_assert(offsetof(Cpu, f) == offsetof(RcCpu, f), "RcCpu layout: " #f)
SAME(mem); SAME(a); SAME(x); SAME(y); SAME(sp); SAME(pc); SAME(dp); SAME(k); SAME(db);
SAME(c); SAME(z); SAME(v); SAME(n); SAME(i); SAME(d); SAME(xf); SAME(mf); SAME(e);
SAME(waiting); SAME(stopped); SAME(irqWanted); SAME(nmiWanted); SAME(intWanted); SAME(intDelay);
SAME(resetWanted); SAME(brk); SAME(icount);
_Static_assert(sizeof(Cpu) == sizeof(RcCpu), "RcCpu size");

// ---- bus helpers (identical sequencing to cpu.c) ----
u8 rcR(RcCpu* c, u32 adr) { c->intDelay = 0; return snes_cpuRead(c->mem, adr); }
void rcW(RcCpu* c, u32 adr, u8 v) { c->intDelay = 0; snes_cpuWrite(c->mem, adr, v); }
void rcI(RcCpu* c) { c->intDelay = 0; snes_cpuIdle(c->mem, false); }
void rcF(RcCpu* c, u32 adr, u8 v) {
  c->intDelay = 0;
  Snes* snes = (Snes*)c->mem;
  const int cycles = snes->access_time[adr] - 4;
  dma_handleDma(snes->dma, cycles + 4);
  snes_runCycles(snes, cycles);
  snes->openBus = v;
  snes_runCycles(snes, 4);
}
void rcCI(RcCpu* c) {
  c->intWanted = (c->nmiWanted || (c->irqWanted && !c->i)) && !c->intDelay;
  c->intDelay = 0;
}
u16 rcRW(RcCpu* c, u32 lo, u32 hi, int ic) {
  u8 v = rcR(c, lo);
  if(ic) rcCI(c);
  return v | (rcR(c, hi) << 8);
}
void rcWW(RcCpu* c, u32 lo, u32 hi, u16 v, int rev, int ic) {
  if(rev) { rcW(c, hi, v >> 8); if(ic) rcCI(c); rcW(c, lo, v & 0xff); }
  else { rcW(c, lo, v & 0xff); if(ic) rcCI(c); rcW(c, hi, v >> 8); }
}
void rcP8(RcCpu* c, u8 v) {
  rcW(c, c->sp, v);
  c->sp--;
  if(c->e) c->sp = (c->sp & 0xff) | 0x100;
}
void rcP16(RcCpu* c, u16 v, int ic) {
  rcP8(c, v >> 8);
  if(ic) rcCI(c);
  rcP8(c, v & 0xff);
}
u8 rcL8(RcCpu* c) {
  c->sp++;
  if(c->e) c->sp = (c->sp & 0xff) | 0x100;
  return rcR(c, c->sp);
}
u16 rcL16(RcCpu* c, int ic) {
  u8 v = rcL8(c);
  if(ic) rcCI(c);
  return v | (rcL8(c) << 8);
}
u8 rcGF(RcCpu* c) {
  return (c->n << 7) | (c->v << 6) | (c->mf << 5) | (c->xf << 4) | (c->d << 3) | (c->i << 2) | (c->z << 1) | c->c;
}
void rcSF(RcCpu* c, u8 val) {
  c->n = val & 0x80; c->v = val & 0x40; c->mf = val & 0x20; c->xf = val & 0x10;
  c->d = val & 8; c->i = val & 4; c->z = val & 2; c->c = val & 1;
  if(c->e) { c->mf = 1; c->xf = 1; c->sp = (c->sp & 0xff) | 0x100; }
  if(c->xf) { c->x &= 0xff; c->y &= 0xff; }
}
void rcIMP(RcCpu* c, u32 nextAdr, u8 nextByte) {
  rcCI(c);
  if(c->intWanted) rcF(c, nextAdr, nextByte);
  else rcI(c);
}
void rcADC8(RcCpu* c, u8 value) {
  int result;
  if(c->d) {
    result = (c->a & 0xf) + (value & 0xf) + c->c;
    if(result > 0x9) result = ((result + 0x6) & 0xf) + 0x10;
    result = (c->a & 0xf0) + (value & 0xf0) + result;
  } else {
    result = (c->a & 0xff) + value + c->c;
  }
  c->v = (c->a & 0x80) == (value & 0x80) && (value & 0x80) != (result & 0x80);
  if(c->d && result > 0x9f) result += 0x60;
  c->c = result > 0xff;
  c->a = (c->a & 0xff00) | (result & 0xff);
  ZN8(c->a);
}
void rcADC16(RcCpu* c, u16 value) {
  int result;
  if(c->d) {
    result = (c->a & 0xf) + (value & 0xf) + c->c;
    if(result > 0x9) result = ((result + 0x6) & 0xf) + 0x10;
    result = (c->a & 0xf0) + (value & 0xf0) + result;
    if(result > 0x9f) result = ((result + 0x60) & 0xff) + 0x100;
    result = (c->a & 0xf00) + (value & 0xf00) + result;
    if(result > 0x9ff) result = ((result + 0x600) & 0xfff) + 0x1000;
    result = (c->a & 0xf000) + (value & 0xf000) + result;
  } else {
    result = c->a + value + c->c;
  }
  c->v = (c->a & 0x8000) == (value & 0x8000) && (value & 0x8000) != (result & 0x8000);
  if(c->d && result > 0x9fff) result += 0x6000;
  c->c = result > 0xffff;
  c->a = result;
  ZN16(c->a);
}
void rcSBC8(RcCpu* c, u8 value) {
  value ^= 0xff;
  int result;
  if(c->d) {
    result = (c->a & 0xf) + (value & 0xf) + c->c;
    if(result < 0x10) result = (result - 0x6) & ((result - 0x6 < 0) ? 0xf : 0x1f);
    result = (c->a & 0xf0) + (value & 0xf0) + result;
  } else {
    result = (c->a & 0xff) + value + c->c;
  }
  c->v = (c->a & 0x80) == (value & 0x80) && (value & 0x80) != (result & 0x80);
  if(c->d && result < 0x100) result -= 0x60;
  c->c = result > 0xff;
  c->a = (c->a & 0xff00) | (result & 0xff);
  ZN8(c->a);
}
void rcSBC16(RcCpu* c, u16 value) {
  value ^= 0xffff;
  int result;
  if(c->d) {
    result = (c->a & 0xf) + (value & 0xf) + c->c;
    if(result < 0x10) result = (result - 0x6) & ((result - 0x6 < 0) ? 0xf : 0x1f);
    result = (c->a & 0xf0) + (value & 0xf0) + result;
    if(result < 0x100) result = (result - 0x60) & ((result - 0x60 < 0) ? 0xff : 0x1ff);
    result = (c->a & 0xf00) + (value & 0xf00) + result;
    if(result < 0x1000) result = (result - 0x600) & ((result - 0x600 < 0) ? 0xfff : 0x1fff);
    result = (c->a & 0xf000) + (value & 0xf000) + result;
  } else {
    result = c->a + value + c->c;
  }
  c->v = (c->a & 0x8000) == (value & 0x8000) && (value & 0x8000) != (result & 0x8000);
  if(c->d && result < 0x10000) result -= 0x6000;
  c->c = result > 0xffff;
  c->a = result;
  ZN16(c->a);
}

// ---- block table (open addressing hash: key = pc24 << 3 | fs) ----
static u32* htKeys; static RcBlockFn* htFns; static u32 htMask; static int htCount;

static inline u32 rc_hash(u32 key) { key *= 0x9E3779B1u; return key ^ (key >> 15); }

void rc_setBlocks(const RcEntry* tab, int n) {
  free(htKeys); free(htFns);
  u32 size = 1024; while(size < (u32)n * 3) size <<= 1;
  htKeys = calloc(size, sizeof(u32)); htFns = calloc(size, sizeof(RcBlockFn)); htMask = size - 1; htCount = 0;
  for(int i = 0; i < n; i++) {
    u32 key = (tab[i].pc << 3) | tab[i].fs | 0x80000000u;
    u32 h = rc_hash(key) & htMask;
    while(htKeys[h] && htKeys[h] != key) h = (h + 1) & htMask;
    if(!htKeys[h]) htCount++;
    htKeys[h] = key; htFns[h] = tab[i].fn;
  }
}

int rc_blockCount(void) { return htCount; }

static inline RcBlockFn rc_lookup(u32 pc24, u32 fs) {
  if(!htKeys) return NULL;
  u32 key = (pc24 << 3) | fs | 0x80000000u;
  u32 h = rc_hash(key) & htMask;
  while(htKeys[h]) { if(htKeys[h] == key) return htFns[h]; h = (h + 1) & htMask; }
  return NULL;
}

static inline u32 rc_fs(Cpu* c) { return c->e ? 4 : ((c->mf << 1) | c->xf); }

// ---- coverage: leaders reached by the interpreter fallback ----
RcStats rc_stats;
static u32* covKeys; static u32* covCount; static u32 covMask; static int covN;
static int lastSeqValid; static u32 lastSeqNext; // previous interpreted op was straight-line, next pc
int rc_recordMisses = 1;

static void cov_add(u32 key) {
  if(!covKeys) { covMask = (1 << 16) - 1; covKeys = calloc(covMask + 1, 4); covCount = calloc(covMask + 1, 4); }
  if((u32)covN * 2 > covMask) {
    u32 om = covMask; u32* ok = covKeys; u32* oc = covCount;
    covMask = om * 2 + 1; covKeys = calloc(covMask + 1, 4); covCount = calloc(covMask + 1, 4); covN = 0;
    for(u32 i = 0; i <= om; i++) if(ok[i]) {
      u32 h = rc_hash(ok[i]) & covMask; while(covKeys[h]) h = (h + 1) & covMask;
      covKeys[h] = ok[i]; covCount[h] = oc[i]; covN++;
    }
    free(ok); free(oc);
  }
  u32 h = rc_hash(key) & covMask;
  while(covKeys[h] && covKeys[h] != key) h = (h + 1) & covMask;
  if(!covKeys[h]) { covKeys[h] = key; covN++; }
  covCount[h]++;
}

int rc_saveCoverage(const char* path, int append) {
  FILE* f = fopen(path, append ? "a" : "w"); if(!f) return 0;
  int n = 0;
  if(covKeys) for(u32 i = 0; i <= covMask; i++) if(covKeys[i]) {
    u32 k = covKeys[i] & 0x7fffffff;
    fprintf(f, "%06X %u %u\n", k >> 3, k & 7, covCount[i]); n++;
  }
  fclose(f);
  return n;
}

void rc_clearCoverage(void) { if(covKeys) { memset(covKeys, 0, (covMask + 1) * 4); memset(covCount, 0, (covMask + 1) * 4); } covN = 0; }

static inline int is_rom(u32 adr) {
  u8 bank = adr >> 16;
  if(bank == 0x7e || bank == 0x7f) return 0;
  if((bank & 0x7f) >= 0x40) return 1;
  return (adr & 0xffff) >= 0x8000;
}

// one CPU step: a compiled block if there is one, otherwise one interpreted opcode
static inline void rc_step(Snes* snes) {
  Cpu* c = snes->cpu;
  if(!(c->resetWanted | c->stopped | c->waiting | c->intWanted)) {
    u32 pc24 = ((u32)c->k << 16) | c->pc;
    u32 fs = rc_fs(c);
    RcBlockFn fn = rc_lookup(pc24, fs);
    if(fn) {
      c->brk = 0;
      fn((RcCpu*)c);
      rc_stats.blocks++;
      lastSeqValid = 0;
      return;
    }
    // interpreted: record leaders (not reached by straight-line flow from the previous interpreted op)
    if(rc_recordMisses && is_rom(pc24) && !(lastSeqValid && lastSeqNext == pc24)) cov_add((pc24 << 3) | fs | 0x80000000u);
    u8 opc = cart_read(snes->cart, c->k, c->pc);
    if(!rc_opEndsBlock(opc)) { lastSeqValid = 1; lastSeqNext = ((u32)c->k << 16) | ((c->pc + rc_opLen(opc, c->mf, c->xf)) & 0xffff); }
    else lastSeqValid = 0;
    rc_stats.interp++;
  } else {
    lastSeqValid = 0;
    rc_stats.special++;
  }
  cpu_runOpcode(c);
  c->icount++;
}

// same loop structure as snes_runFrame()
void rc_runFrame(Snes* snes) {
  while(snes->inVblank) rc_step(snes);
  uint32_t frame = snes->frames;
  while(!snes->inVblank && frame == snes->frames) rc_step(snes);
}

void rc_stepOnce(Snes* snes) { rc_step(snes); }
