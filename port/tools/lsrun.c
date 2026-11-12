// Headless LakeSnes runner for testing.
// lsrun rom.sfc movie.txt frames outdir [shot frames comma list] [--state-out f N] [--state-in f]
// movie.txt: lines "<frame> <buttons>" - from that frame on hold the buttons
//   buttons letters: B Y s S U D L R A X l r  ('-' = none)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "snes.h"
#include "ppu.h"
#include "fe4wide.h"
#include "cart.h"
#include "cpu.h"
static uint32_t* wideBuf; static int wideOn;

static const char* BTN = "BYsSUDLRAXlr";

typedef struct { int frame; uint16_t mask; } MovieEv;
static MovieEv ev[100000]; static int nev;

static uint16_t parse_btn(const char* s) {
  uint16_t m = 0;
  for(; *s && *s != '\n' && *s != '\r'; s++) { const char* p = strchr(BTN, *s); if(p && *s != '-') m |= 1 << (p - BTN); }
  return m;
}

static void load_movie(const char* path) {
  FILE* f = fopen(path, "r"); if(!f) return;
  char line[256];
  while(fgets(line, sizeof line, f)) {
    if(line[0] == '#' || line[0] == '\n') continue;
    int fr; char b[64] = "-";
    if(sscanf(line, "%d %63s", &fr, b) >= 1) { ev[nev].frame = fr; ev[nev].mask = parse_btn(b); nev++; }
  }
  fclose(f);
}

static uint16_t movie_mask(int frame) {
  uint16_t m = 0;
  for(int i = 0; i < nev && ev[i].frame <= frame; i++) m = ev[i].mask;
  return m;
}

void write_ppm(Snes* snes, const char* path) {
  static uint8_t px[512 * 480 * 4];
  if(wideOn) {
    FILE* f = fopen(path, "wb");
    fprintf(f, "P6 %d 224 255\n", FE4WIDE_W);
    for(int y = 0; y < 224; y++) for(int x = 0; x < FE4WIDE_W; x++) {
      uint32_t c = wideBuf[y * FE4WIDE_W + x]; uint8_t rgb[3] = { c >> 16, c >> 8, c };
      fwrite(rgb, 1, 3, f);
    }
    fclose(f); return;
  }
  snes_setPixels(snes, px);
  FILE* f = fopen(path, "wb");
  fprintf(f, "P6 256 224 255\n");
  for(int y = 0; y < 224; y++) for(int x = 0; x < 256; x++) {
    uint8_t* p = &px[((16 + y * 2) * 512 + x * 2) * 4];
    // LakeSnes pixel format: BGRX
    uint8_t rgb[3] = { p[2], p[1], p[0] };
    fwrite(rgb, 1, 3, f);
  }
  fclose(f);
}

static uint8_t* read_file(const char* path, int* len) {
  FILE* f = fopen(path, "rb"); if(!f) return NULL;
  fseek(f, 0, SEEK_END); *len = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t* d = malloc(*len); fread(d, 1, *len, f); fclose(f); return d;
}

static uint32_t watchLo, watchHi; static int watching;
static void write_hook(Snes* s, uint32_t adr, uint8_t val) {
  if(!watching) return;
  uint8_t bank = adr >> 16; uint32_t a = adr & 0xffff, w;
  if(bank == 0x7e || bank == 0x7f) w = ((bank & 1) << 16) | a;
  else if(((bank & 0x7f) < 0x40) && a < 0x2000) w = a; else return;
  if(w >= watchLo && w <= watchHi) {
    printf("W %05X=%02X pc=%02X:%04X a=%04X x=%04X y=%04X dp=%04X db=%02X sp=%04X stk:", w, val, s->cpu->k, s->cpu->pc, s->cpu->a, s->cpu->x, s->cpu->y, s->cpu->dp, s->cpu->db, s->cpu->sp);
    for(int i = 1; i <= 24; i++) printf(" %02X", s->ram[(s->cpu->sp + i) & 0xffff]);
    printf("\n");
  }
}
static Snes* gSnes; static int retWatch[8], nRetWatch, execOn;
static uint32_t tracePcs[32]; static int nTracePcs = -1;
static void exec_hook(Cpu* c) {
  if(!execOn) return;
  if(nTracePcs < 0) { nTracePcs = 0; const char* t = getenv("TRACEPC"); while(t && *t && nTracePcs < 32) { char* e; tracePcs[nTracePcs++] = strtol(t, &e, 16); t = *e ? e + 1 : e; } }
  for(int i = 0; i < nTracePcs; i++) if(((uint32_t)c->k << 16 | c->pc) == tracePcs[i]) {
    uint8_t* s = gSnes->ram; uint16_t sp = c->sp;
    printf("PC %02X:%04X A=%04X X=%04X Y=%04X DB=%02X DP:", c->k, c->pc, c->a, c->x, c->y, c->db);
    for(int k = 0; k < 0x10; k++) printf(" %02X", s[0xC0 + k]);
    printf(" ret %02X%02X%02X\n", s[(sp + 3) & 0xffff], s[(sp + 2) & 0xffff], s[(sp + 1) & 0xffff]);
  }
  uint8_t op = cart_read(gSnes->cart, c->k, c->pc);
  if(c->k >= 0x7e && c->k <= 0x7f) return;
  if(op != 0x6B && op != 0x60) return;
  int a = c->mf ? (c->a & 0xff) : c->a;
  for(int i = 0; i < nRetWatch; i++) if(a == retWatch[i]) {
    uint8_t* s = gSnes->ram; uint16_t sp = c->sp;
    uint32_t ret = op == 0x6B ? ((s[(sp + 3) & 0xffff] << 16) | (s[(sp + 2) & 0xffff] << 8) | s[(sp + 1) & 0xffff]) + 1
                              : ((c->k << 16) | (s[(sp + 2) & 0xffff] << 8) | s[(sp + 1) & 0xffff]) + 1;
    printf("RET %s at %02X:%04X A=%d -> %06X\n", op == 0x6B ? "RTL" : "RTS", c->k, c->pc, a, ret);
  }
}
static int dmaFrame, dmaOn, dmaLo, dmaHi;
static void dma_log(Dma* d, int ch) {
  if(!dmaOn) return;
  Ppu* p = gSnes->ppu;
  printf("DMA %d ch%d %02X:%04X n=%04X b=21%02X mode=%d%s vram=%04X cg=%02X\n", dmaFrame, ch, d->channel[ch].aBank, d->channel[ch].aAdr,
         d->channel[ch].size, d->channel[ch].bAdr, d->channel[ch].mode, d->channel[ch].fromB ? " fromB" : "", p->vramPointer, p->cgramPointer);
}
static uint32_t frzAdr[16]; static uint8_t frzVal[16]; static int nFrz, frzOn;
static uint8_t freeze_map(Snes* s, uint32_t adr, uint8_t val) {
  if(!frzOn) return val;
  uint8_t bank = adr >> 16; uint32_t a = adr & 0xffff, w;
  if(bank == 0x7e || bank == 0x7f) w = ((bank & 1) << 16) | a;
  else if(((bank & 0x7f) < 0x40) && a < 0x2000) w = a; else return val;
  for(int i = 0; i < nFrz; i++) if(frzAdr[i] == w) return frzVal[i];
  return val;
}
static FILE* lineLog;
static int line60Battle; static int battleEvery;
static void battle_hook(Ppu* p, int line) { if(line == 60) line60Battle = p->mode == 1 && p->bgLayer[1].tilemapAdr == 0x6000 && p->bgLayer[1].tilemapWider && p->layer[1].mainScreenEnabled && p->brightness == 15; }
static int regLine = -1; static int regFrame;
static void line_hook(Ppu* p, int line) {
  if(regLine >= 0) { if(line != regLine) return; lineLog = stdout; fprintf(stdout, "F%d ", regFrame); }
  if(!lineLog) return;
  fprintf(lineLog, "%d mode=%d bg3p=%d main=%d%d%d%d%d sub=%d%d%d%d%d", line, p->mode, p->bg3priority,
    p->layer[0].mainScreenEnabled, p->layer[1].mainScreenEnabled, p->layer[2].mainScreenEnabled, p->layer[3].mainScreenEnabled, p->layer[4].mainScreenEnabled,
    p->layer[0].subScreenEnabled, p->layer[1].subScreenEnabled, p->layer[2].subScreenEnabled, p->layer[3].subScreenEnabled, p->layer[4].subScreenEnabled);
  for(int i = 0; i < 4; i++) fprintf(lineLog, " bg%d:h=%d,v=%d,map=%04X%s%s,chr=%04X%s", i + 1, p->bgLayer[i].hScroll, p->bgLayer[i].vScroll,
    p->bgLayer[i].tilemapAdr, p->bgLayer[i].tilemapWider ? "W" : "", p->bgLayer[i].tilemapHigher ? "H" : "", p->bgLayer[i].tileAdr, p->bgLayer[i].bigTiles ? "B" : "");
  fprintf(lineLog, " win1=%d-%d win2=%d-%d fb=%d bright=%d\n", p->window1left, p->window1right, p->window2left, p->window2right, p->forcedBlank, p->brightness);
}

int main(int argc, char** argv) {
  if(argc < 5) { fprintf(stderr, "usage: lsrun rom movie frames outdir [shots] [--state-out f N] [--state-in f] [--ram f]\n"); return 1; }
  int len; uint8_t* rom = read_file(argv[1], &len);
  for(int i = 5; i < argc; i++) if(!strcmp(argv[i], "--wide") || !strcmp(argv[i], "--widetest")) wideOn = 1;
  if(wideOn) fprintf(stderr, "widescreen patches applied: %d\n", fe4wide_patchRom(rom, len));
  Snes* snes = snes_init();
  if(!snes_loadRom(snes, rom, len)) return 1;
  if(wideOn) { wideBuf = calloc(FE4WIDE_W * 239, 4); fe4wide_attach(snes, wideBuf); }
  gSnes = snes;
  load_movie(argv[2]);
  int frames = atoi(argv[3]);
  const char* outdir = argv[4];
  int shots[1000], nshots = 0;
  const char* stateOut = NULL; int stateOutFrame = -1; const char* ramOut = NULL; const char* dumpPrefix = NULL;
  int startFrame = 0;
  for(int i = 5; i < argc; i++) {
    if(!strcmp(argv[i], "--state-out")) { stateOut = argv[++i]; stateOutFrame = atoi(argv[++i]); }
    else if(!strcmp(argv[i], "--state-in")) {
      int sl; uint8_t* sd = read_file(argv[++i], &sl);
      if(!snes_loadState(snes, sd + 4, sl - 4)) { fprintf(stderr, "bad state\n"); return 1; }
      startFrame = *(int*)sd;
    }
    else if(!strcmp(argv[i], "--ram")) ramOut = argv[++i];
    else if(!strcmp(argv[i], "--dump")) dumpPrefix = argv[++i];
    else if(!strcmp(argv[i], "--wide")) {}
    else if(!strcmp(argv[i], "--rets")) { char* s = argv[++i]; while(*s) { retWatch[nRetWatch++] = strtol(s, &s, 10); if(*s == ',') s++; } cpu_execHook = exec_hook; }
    else if(!strcmp(argv[i], "--battles")) { battleEvery = atoi(argv[++i]); ppu_lineHook = battle_hook; }
    else if(!strcmp(argv[i], "--widetest")) { wideOn = 1; fe4wide_selftest = 1; }
    else if(!strcmp(argv[i], "--freeze")) { frzAdr[nFrz] = strtol(argv[++i], NULL, 16); frzVal[nFrz++] = strtol(argv[++i], NULL, 16); snes_writeMap = freeze_map; }
    else if(!strcmp(argv[i], "--dma")) { dmaLo = atoi(argv[++i]); dmaHi = atoi(argv[++i]); dma_logHook = dma_log; }
    else if(!strcmp(argv[i], "--watch")) { watchLo = strtol(argv[++i], NULL, 16); watchHi = strtol(argv[++i], NULL, 16); snes_writeHook = write_hook; }
    else { char* s = argv[i]; while(*s) { shots[nshots++] = strtol(s, &s, 10); if(*s == ',') s++; } }
  }
  if(getenv("TRACEPC")) cpu_execHook = exec_hook;
  for(int fr = startFrame; fr < frames; fr++) {
    uint16_t m = movie_mask(fr);
    for(int b = 0; b < 12; b++) snes_setButtonState(snes, 1, b, (m >> b) & 1);
    execOn = fr >= (getenv("EXECFROM") ? atoi(getenv("EXECFROM")) : 0);
    watching = fr >= (getenv("WATCHFROM") ? atoi(getenv("WATCHFROM")) : frames - 10);
    dmaFrame = fr; dmaOn = fr >= dmaLo && fr <= dmaHi;
    frzOn = fr >= (getenv("FREEZEFROM") ? atoi(getenv("FREEZEFROM")) : 0);
    if(getenv("REGLOG")) { regLine = atoi(getenv("REGLOG")); regFrame = fr; ppu_lineHook = line_hook; }
    if(dumpPrefix && fr == frames - 1) { char p[512]; snprintf(p, sizeof p, "%s.lines", dumpPrefix); lineLog = fopen(p, "w"); ppu_lineHook = line_hook; }
    snes_runFrame(snes);
    if(wideOn && getenv("OAMSTAT")) {
      static int maxUsed = 0, maxFrame = 0;
      int used = 0;
      for(int i = 0; i < 128; i++) { uint8_t y = snes->ppu->oam[i * 2] >> 8; if(y < 224 || y > 0xf8) used++; }
      if(used > maxUsed) { maxUsed = used; maxFrame = fr; }
      if(fr == frames - 1) printf("max sprites in use: %d (frame %d)\n", maxUsed, maxFrame);
    }
    if(fe4wide_selftest) {
      long diff = 0, total = 0;
      for(int y = 9; y < 216; y++) {
        const uint32_t* src = (const uint32_t*)&snes->ppu->pixelBuffer[((y - 1) + (snes->ppu->evenFrame ? 0 : 239)) * 2048];
        const uint32_t* wr = wideBuf + (y - 1) * FE4WIDE_W + FE4WIDE_EXT;
        for(int x = 8; x < 248; x++) { total++; if((src[x * 2 + 1] & 0xffffff) != (wr[x] & 0xffffff)) diff++; }
      }
      if(diff) printf("frame %d: %ld of %ld pixels differ\n", fr, diff, total);
      else if(fr % 500 == 0) printf("frame %d: identical\n", fr);
    }
    { static int lastB = -100000;
      if(battleEvery && line60Battle && fr - lastB >= battleEvery) { lastB = fr; char p[512]; snprintf(p, sizeof p, "%s/b%06d.ppm", outdir, fr); write_ppm(snes, p); } }
    if(getenv("BATTLECHECK")) { // compare the end-of-frame register check with the line-60 check
      static int agree, disagree; Ppu* p = snes->ppu;
      int endB = p->mode == 1 && p->bgLayer[1].tilemapAdr == 0x6000 && p->bgLayer[1].tilemapWider;
      if(endB == line60Battle) agree++; else disagree++;
      static int runStart = -1, runHasLine = 0, lineOnly = 0;
      if(endB) { if(runStart < 0) { runStart = fr; runHasLine = 0; } if(line60Battle) runHasLine = 1; }
      else { if(runStart >= 0) printf("battle-ish run %d-%d (%d frames) line60 %s\n", runStart, fr - 1, fr - runStart, runHasLine ? "yes" : "NO"); runStart = -1; if(line60Battle) lineOnly++; }
      if(fr == frames - 1) printf("line60 without end check: %d frames\n", lineOnly);
      if(fr == frames - 1) printf("agree %d disagree %d\n", agree, disagree);
    }
    if(getenv("BATTLELOG")) { static FILE* bl; if(!bl) bl = fopen(getenv("BATTLELOG"), "w"); if(line60Battle) fprintf(bl, "%d\n", fr); }
    { static FILE* rl; static int every = -1;   // RAMLOG=file RAMEVERY=n: low 8 KB of WRAM every n frames
      if(every < 0) { every = getenv("RAMEVERY") ? atoi(getenv("RAMEVERY")) : 0; if(every && getenv("RAMLOG")) rl = fopen(getenv("RAMLOG"), "wb"); }
      if(rl && fr % every == 0) { fwrite(&fr, 4, 1, rl); fwrite(snes->ram, 1, 0x2000, rl); } }
    for(int i = 0; i < nshots; i++) if(shots[i] == fr) {
      char p[512]; snprintf(p, sizeof p, "%s/f%06d.ppm", outdir, fr); write_ppm(snes, p);
    }
    if(stateOut && fr == stateOutFrame) {
      int sz = snes_saveState(snes, NULL); uint8_t* d = malloc(sz + 4);
      *(int*)d = fr + 1; snes_saveState(snes, d + 4);
      FILE* f = fopen(stateOut, "wb"); fwrite(d, 1, sz + 4, f); fclose(f); free(d);
    }
  }
  if(dumpPrefix) {
    if(lineLog) fclose(lineLog);
    char p[512];
    snprintf(p, sizeof p, "%s.vram", dumpPrefix); FILE* f = fopen(p, "wb"); fwrite(snes->ppu->vram, 1, 0x10000, f); fclose(f);
    snprintf(p, sizeof p, "%s.cgram", dumpPrefix); f = fopen(p, "wb"); fwrite(snes->ppu->cgram, 1, 0x200, f); fclose(f);
    snprintf(p, sizeof p, "%s.oam", dumpPrefix); f = fopen(p, "wb"); fwrite(snes->ppu->oam, 1, 0x200, f); fwrite(snes->ppu->highOam, 1, 0x20, f); fclose(f);
    snprintf(p, sizeof p, "%s.wram", dumpPrefix); f = fopen(p, "wb"); fwrite(snes->ram, 1, 0x20000, f); fclose(f);
  }
  if(ramOut) { FILE* f = fopen(ramOut, "wb"); fwrite(snes->ram, 1, 0x20000, f); fclose(f); }
  char p[512]; snprintf(p, sizeof p, "%s/last.ppm", outdir); write_ppm(snes, p);
  printf("frames=%d cycles=%llu pc=%02x:%04x\n", frames, (unsigned long long)snes->cycles, snes->cpu->k, snes->cpu->pc);
  return 0;
}
