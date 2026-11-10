// Lockstep verifier: machine A runs the LakeSnes interpreter, machine B runs recompiled code.
// After every block B executes, A is advanced by the same number of instructions and the full
// CPU state, cycle counter and beam position must match. Every frame, WRAM/VRAM/CGRAM/OAM,
// SRAM and APU RAM must match too.
//
// lockstep rom.sfc movie.txt frames [--shots outdir f1,f2..] [--cov out.txt] [--nocheck] [--state-out f N] [--state-in f]
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "snes.h"
#include "apu.h"
#include "spc.h"
#include "ppu.h"
#include "cart.h"
#include "rc_rt.h"
#include "movie.h"

#ifdef USE_JIT
#include "rc_jit.h"
#else
extern const RcEntry rc_blocks[];
extern const int rc_blockCountGen;
#endif

static uint8_t* read_file(const char* path, int* len) {
  FILE* f = fopen(path, "rb"); if(!f) return NULL;
  fseek(f, 0, SEEK_END); *len = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t* d = malloc(*len); fread(d, 1, *len, f); fclose(f); return d;
}

static void write_ppm(Snes* snes, const char* path) {
  static uint8_t px[512 * 480 * 4];
  snes_setPixels(snes, px);
  FILE* f = fopen(path, "wb");
  fprintf(f, "P6 256 224 255\n");
  for(int y = 0; y < 224; y++) for(int x = 0; x < 256; x++) {
    uint8_t* p = &px[((16 + y * 2) * 512 + x * 2) * 4];
    uint8_t rgb[3] = { p[2], p[1], p[0] };
    fwrite(rgb, 1, 3, f);
  }
  fclose(f);
}

static int cpu_eq(Cpu* a, Cpu* b) {
  return a->a == b->a && a->x == b->x && a->y == b->y && a->sp == b->sp && a->pc == b->pc && a->dp == b->dp &&
    a->k == b->k && a->db == b->db && a->c == b->c && a->z == b->z && a->v == b->v && a->n == b->n &&
    a->i == b->i && a->d == b->d && a->xf == b->xf && a->mf == b->mf && a->e == b->e &&
    a->waiting == b->waiting && a->stopped == b->stopped && a->irqWanted == b->irqWanted &&
    a->nmiWanted == b->nmiWanted && a->intWanted == b->intWanted && a->intDelay == b->intDelay;
}

static void dump_cpu(const char* tag, Snes* s) {
  Cpu* c = s->cpu;
  fprintf(stderr, "%s pc=%02X:%04X a=%04X x=%04X y=%04X sp=%04X dp=%04X db=%02X P=%c%c%c%c%c%c%c%c e=%d iw=%d nw=%d id=%d cyc=%llu h=%d v=%d ob=%02X ic=%llu\n",
    tag, c->k, c->pc, c->a, c->x, c->y, c->sp, c->dp, c->db,
    c->n ? 'N' : 'n', c->v ? 'V' : 'v', c->mf ? 'M' : 'm', c->xf ? 'X' : 'x', c->d ? 'D' : 'd', c->i ? 'I' : 'i', c->z ? 'Z' : 'z', c->c ? 'C' : 'c',
    c->e, c->intWanted, c->nmiWanted, c->intDelay, (unsigned long long)s->cycles, s->hPos, s->vPos, s->openBus, (unsigned long long)c->icount);
}

static int mem_eq(const char* what, const void* a, const void* b, int n) {
  if(!memcmp(a, b, n)) return 1;
  const uint8_t* x = a; const uint8_t* y = b;
  for(int i = 0; i < n; i++) if(x[i] != y[i]) { fprintf(stderr, "%s differs at %05X: %02X vs %02X\n", what, i, x[i], y[i]); break; }
  return 0;
}

int main(int argc, char** argv) {
  if(argc < 4) { fprintf(stderr, "usage: lockstep rom movie frames [--shots dir list] [--cov f] [--nocheck]\n"); return 1; }
  int len; uint8_t* rom = read_file(argv[1], &len);
  movie_load(argv[2]);
  int frames = atoi(argv[3]);
  const char* shotDir = NULL; int shots[4096], nshots = 0; const char* covOut = NULL; int check = 1;
  const char* stateOut = NULL; int stateOutFrame = -1; const char* stateIn = NULL;
  for(int i = 4; i < argc; i++) {
    if(!strcmp(argv[i], "--shots")) { shotDir = argv[++i]; char* s = argv[++i]; while(*s) { shots[nshots++] = strtol(s, &s, 10); if(*s == ',') s++; } }
    else if(!strcmp(argv[i], "--cov")) covOut = argv[++i];
    else if(!strcmp(argv[i], "--nocheck")) check = 0;
    else if(!strcmp(argv[i], "--state-out")) { stateOut = argv[++i]; stateOutFrame = atoi(argv[++i]); }
    else if(!strcmp(argv[i], "--state-in")) stateIn = argv[++i];
  }
  Snes* A = snes_init(); Snes* B = snes_init();
  if(!snes_loadRom(A, rom, len) || !snes_loadRom(B, rom, len)) return 1;
  int startFrame = 0;
  if(stateIn) {
    int sl; uint8_t* sd = read_file(stateIn, &sl);
    startFrame = *(int*)sd;
    if(!snes_loadState(A, sd + 4, sl - 4) || !snes_loadState(B, sd + 4, sl - 4)) { fprintf(stderr, "bad state\n"); return 1; }
    A->cpu->icount = B->cpu->icount = 0;
  }
#ifdef USE_JIT
  {
    const char* src = getenv("RC_SRC") ? getenv("RC_SRC") : "work/gen.c";
    int sl; char* text = (char*)read_file(src, &sl); text = realloc(text, sl + 1); text[sl] = 0;
    const RcEntry* tab; int n; void* h; clock_t j0 = clock();
    if(!rc_jitCompile(text, &tab, &n, &h)) { fprintf(stderr, "jit failed:\n%s", rc_jitError()); return 4; }
    fprintf(stderr, "jit compiled %d blocks in %.2fs\n", n, (double)(clock() - j0) / CLOCKS_PER_SEC);
    rc_setBlocks(tab, n);
  }
#else
  rc_setBlocks(rc_blocks, rc_blockCountGen);
#endif
  fprintf(stderr, "blocks: %d\n", rc_blockCount());
  clock_t t0 = clock();
  unsigned long long steps = 0;
  for(int fr = startFrame; fr < frames; fr++) {
    uint16_t m = movie_mask(fr);
    for(int b = 0; b < 12; b++) { snes_setButtonState(A, 1, b, (m >> b) & 1); snes_setButtonState(B, 1, b, (m >> b) & 1); }
    // B: same loop structure as snes_runFrame, one step (block or interpreted op) at a time
    int phase = 0; uint32_t frame0 = 0;
    for(;;) {
      if(phase == 0) { if(!B->inVblank) { phase = 1; frame0 = B->frames; continue; } }
      else if(B->inVblank || frame0 != B->frames) break;
      uint32_t pcBefore = (B->cpu->k << 16) | B->cpu->pc; uint64_t icBefore = B->cpu->icount;
      Cpu saveB = *B->cpu;
      rc_stepOnce(B);
      steps++;
      if(check) {
        while(A->cpu->icount < B->cpu->icount) { cpu_runOpcode(A->cpu); A->cpu->icount++; }
        if(!cpu_eq(A->cpu, B->cpu) || A->cycles != B->cycles || A->hPos != B->hPos || A->vPos != B->vPos || A->openBus != B->openBus) {
          fprintf(stderr, "MISMATCH frame %d after step from %06X (fs m=%d x=%d e=%d) icount %llu -> %llu\n",
            fr, pcBefore, saveB.mf, saveB.xf, saveB.e, (unsigned long long)icBefore, (unsigned long long)B->cpu->icount);
          dump_cpu("interp", A); dump_cpu("recomp", B);
          return 2;
        }
      }
    }
    if(check) {
      int ok = mem_eq("WRAM", A->ram, B->ram, 0x20000) && mem_eq("VRAM", A->ppu->vram, B->ppu->vram, sizeof A->ppu->vram) &&
        mem_eq("CGRAM", A->ppu->cgram, B->ppu->cgram, sizeof A->ppu->cgram) && mem_eq("OAM", A->ppu->oam, B->ppu->oam, sizeof A->ppu->oam) &&
        mem_eq("APURAM", A->apu->ram, B->apu->ram, 0x10000) &&
        (A->cart->ramSize == 0 || mem_eq("SRAM", A->cart->ram, B->cart->ram, A->cart->ramSize));
      if(!ok) { fprintf(stderr, "memory mismatch at end of frame %d\n", fr); return 3; }
    }
    if(shotDir) for(int i = 0; i < nshots; i++) if(shots[i] == fr) {
      char p[512]; snprintf(p, sizeof p, "%s/f%06d.ppm", shotDir, fr); write_ppm(B, p);
    }
    if(stateOut && fr == stateOutFrame) {
      int sz = snes_saveState(B, NULL); uint8_t* d = malloc(sz + 4);
      *(int*)d = fr + 1; snes_saveState(B, d + 4);
      FILE* f = fopen(stateOut, "wb"); fwrite(d, 1, sz + 4, f); fclose(f); free(d);
    }
    if(fr % 2000 == 0) fprintf(stderr, "frame %d  blocks %llu interp %llu special %llu\n", fr, rc_stats.blocks, rc_stats.interp, rc_stats.special);
  }
  double secs = (double)(clock() - t0) / CLOCKS_PER_SEC;
  fprintf(stderr, "done %d frames in %.1fs; steps %llu; compiled blocks run %llu, interpreted ops %llu, special %llu\n",
    frames - startFrame, secs, steps, rc_stats.blocks, rc_stats.interp, rc_stats.special);
  if(covOut) fprintf(stderr, "coverage entries written: %d\n", rc_saveCoverage(covOut, 0));
  if(shotDir) { char p[512]; snprintf(p, sizeof p, "%s/last.ppm", shotDir); write_ppm(B, p); }
  printf("OK frames=%d icount=%llu cycles=%llu\n", frames, (unsigned long long)B->cpu->icount, (unsigned long long)B->cycles);
  return 0;
}
