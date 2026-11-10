// FE4 widescreen: decides, line by line, what the area beyond the original 256 pixels shows,
// using only data the game already has:
//  - map screen: the map's own tile layout and tile definitions in RAM, drawn with the tiles and
//    palettes the game has loaded into video memory;
//  - battle screen: the battle background, whose art in video memory is wider than the screen;
//  - everything else: black sides (the original 4:3 picture is left untouched).
#include <string.h>
#include "fe4wide.h"
#include "ppu.h"

// RAM locations (bank $7E/$7F offsets into snes->ram)
#define MAP_TILEDEFS  0x10000  // $7F:0000: 8 bytes per 16x16 map tile: TL, BL, TR, BR tilemap words
#define MAP_GRID      0x12400  // $7F:2400: 16-bit map tile numbers, 64 per row
#define MAP_GRID_ROW  0x80
#define CAM_LIMITS    0x0740   // $7E:0740: camera min x, max x, min y, max y (pixels)
#define RANGE_GRID    0x179EE  // $7E:79EE + y*64 + x: 0 = none, $80 = attack border, else reachable

int fe4wide_selftest; // redraw the whole 256-wide picture through the extension path (testing)

static uint16_t rd16(const Snes* s, uint32_t a) { return s->ram[a] | (s->ram[a + 1] << 8); }

// the area the game lets the camera show: [x0, x1) x [y0, y1)
typedef struct { int x0, x1, y0, y1; } Bounds;
static int map_bounds(const Snes* s, Bounds* b) {
  int minx = rd16(s, CAM_LIMITS), maxx = rd16(s, CAM_LIMITS + 2), miny = rd16(s, CAM_LIMITS + 4), maxy = rd16(s, CAM_LIMITS + 6);
  b->x0 = minx; b->x1 = maxx + 256; b->y0 = miny; b->y1 = maxy + 224;
  return minx <= maxx && miny <= maxy && b->x1 <= 1024 && b->y1 <= 1024;
}
static int map_dims(const Snes* s, int* w, int* h) { Bounds b; *w = *h = 0; return map_bounds(s, &b); }

static int is_map_line(const Ppu* p) {
  const BgLayer* b = &p->bgLayer[0];
  return p->mode == 1 && b->tilemapAdr == 0x5000 && b->tileAdr == 0x0000 && !b->tilemapWider && !b->tilemapHigher &&
    p->layer[0].mainScreenEnabled;
}

static int is_battle_bg_line(const Ppu* p) {
  const BgLayer* b = &p->bgLayer[1];
  return p->mode == 1 && b->tilemapAdr == 0x6000 && b->tilemapWider && p->layer[1].mainScreenEnabled;
}

static uint16_t map_tile(Ppu* p, int layer, int px, int py, bool* opaque, void* ctx);

// Once per frame: does what the game shows in its 256-wide view match what the RAM data predicts?
// Only layers that match are extended, so a screen that reuses these layers for something else
// never gets wrong tiles in the extra area.
typedef struct { Snes* s; uint32_t frame; int checked, mapOk, rangeOk; } Ctx;
static Ctx ctxs[4]; static int nctx;

static void validate(Ppu* p, Ctx* c) {
  int bad1 = 0, bad3 = 0, n = 0;
  const BgLayer* b1 = &p->bgLayer[0]; const BgLayer* b3 = &p->bgLayer[2];
  for(int sy = 16; sy < 208; sy += 16) for(int sx = 16; sx < 240; sx += 16) {
    int wx = sx + b1->hScroll, wy = sy + 1 + b1->vScroll;
    uint16_t ring = p->vram[(0x5000 + ((wy >> 3) & 31) * 32 + ((wx >> 3) & 31)) & 0x7fff];
    bool op; uint16_t pred = map_tile(p, 0, wx, wy, &op, c->s);
    n++;
    if(!op || pred != ring) bad1++;
    int ux = sx + b3->hScroll, uy = sy + 1 + b3->vScroll;
    uint16_t r3 = p->vram[(b3->tilemapAdr + ((uy >> 3) & 31) * 32 + ((ux >> 3) & 31)) & 0x7fff];
    uint16_t p3 = map_tile(p, 2, ux, uy, &op, c->s);
    if(op ? (p3 != r3) : (r3 != 0x00FF)) bad3++;
  }
  c->mapOk = bad1 <= n / 20;   // allow a few tiles mid-update (map events)
  c->rangeOk = bad3 <= 2;
}

static void policy(Ppu* p, int line, PpuWideLine* out, void* ctx) {
  Ctx* c = (Ctx*)ctx;
  Snes* s = c->s;
  (void)line;
  int w, h;
  if(is_map_line(p) && map_dims(s, &w, &h)) {
    if(!c->checked || c->frame != s->frames) { validate(p, c); c->frame = s->frames; c->checked = 1; }
  }
  if(is_map_line(p) && map_dims(s, &w, &h) && c->mapOk) {
    out->enabled = true;
    out->innerFix = fe4wide_selftest ? 128 : 8; // the game masks 8 columns at each edge to hide tile streaming
    out->layerMode[0] = PPU_WIDE_VIRTUAL;
    out->layerMode[1] = PPU_WIDE_HIDE;
    // BG3 scrolling with the map = movement/attack range overlay
    const BgLayer* b3 = &p->bgLayer[2];
    out->layerMode[2] = (b3->tilemapAdr == 0x5800 && b3->hScroll == p->bgLayer[0].hScroll && b3->vScroll == p->bgLayer[0].vScroll && c->rangeOk)
      ? PPU_WIDE_VIRTUAL : PPU_WIDE_HIDE;
    out->layerMode[3] = PPU_WIDE_HIDE;
    return;
  }
  if(is_battle_bg_line(p)) {
    out->enabled = true;
    out->layerMode[0] = PPU_WIDE_HIDE;
    out->layerMode[1] = PPU_WIDE_NORMAL;
    // Battle backgrounds: sky/scenery rows are 400 pixels of art (x 56..455) with one filler tile repeated
    // outside; ground rows are real art across the whole 512. Clip only rows whose outside is filler.
    const BgLayer* b2 = &p->bgLayer[1];
    int row = ((line + b2->vScroll) >> 3) & 31;
    uint16_t first = p->vram[(b2->tilemapAdr + row * 32 + 0) & 0x7fff];
    bool filler = true;
    for(int col = 0; col < 64 && filler; col++) {
      if(col == 7) col = 57;
      uint16_t t = p->vram[(b2->tilemapAdr + (col >> 5) * 0x400 + row * 32 + (col & 31)) & 0x7fff];
      if(t != first) filler = false;
    }
    if(filler) { out->clipLo[1] = 56; out->clipHi[1] = 456; }
    out->layerMode[2] = PPU_WIDE_HIDE;
    out->layerMode[3] = PPU_WIDE_HIDE;
    return;
  }
}

// map tile word for world pixel (px, py): BG1 = terrain, BG3 = range overlay
static uint16_t map_tile(Ppu* p, int layer, int px, int py, bool* opaque, void* ctx) {
  Snes* s = (Snes*)ctx;
  if(ctx >= (void*)ctxs && ctx < (void*)(ctxs + 4)) s = ((Ctx*)ctx)->s;
  (void)p;
  *opaque = false;
  Bounds bd;
  py &= 0x3ff; // vertical scroll wraps (camera y = vScroll + 1)
  if(!map_bounds(s, &bd) || px < bd.x0 || py < bd.y0 || px >= bd.x1 || py >= bd.y1) return 0;
  if(layer == 2) {
    uint8_t v = s->ram[RANGE_GRID + (py >> 4) * 64 + (px >> 4)];
    if(!v) return 0;
    static const uint16_t quad[4] = { 0x4E, 0x5E, 0x4F, 0x5F }; // TL, BL, TR, BR
    *opaque = true;
    return 0x2000 | ((v & 0x80) ? 0x0C00 : 0x0800) | quad[((px >> 3) & 1) * 2 + ((py >> 3) & 1)];
  }
  uint16_t idx = rd16(s, MAP_GRID + (py >> 4) * MAP_GRID_ROW + (px >> 4) * 2);
  if(idx >= 0x400) return 0;
  int q = ((px >> 3) & 1) * 2 + ((py >> 3) & 1);
  *opaque = true;
  return rd16(s, MAP_TILEDEFS + idx * 8 + q * 2);
}

// ROM changes that let the game itself draw units in the extra area: the unit window
// (normally from 1 tile left of the camera, 18 tiles wide) is chosen by a flag word in ROM,
// so widescreen can be switched on and off while playing (see tools/fe4widepatch.py)
#include "fe4wide_data.h"

int fe4wide_patchRom(uint8_t* rom, int len) {
  if(!fe4patch_apply(rom, len, FE4_WIDE)) return 0;
  fe4wide_setRomFlag(rom, len, 1);
  return 1;
}

void fe4wide_setRomFlag(uint8_t* rom, int len, int on) {
  if(FE4_WIDE_FLAG + 1 < (unsigned)len) { rom[FE4_WIDE_FLAG] = on ? 1 : 0; rom[FE4_WIDE_FLAG + 1] = 0; }
}

void fe4wide_attach(Snes* snes, uint32_t* buf) {
  Ppu* p = snes->ppu;
  p->wideExt = FE4WIDE_EXT;
  p->wideBuf = buf;
  p->widePolicy = policy;
  p->wideTile = map_tile;
  Ctx* c = nctx < 4 ? &ctxs[nctx++] : &ctxs[3];
  memset(c, 0, sizeof *c); c->s = snes;
  p->wideCtx = c;
}
