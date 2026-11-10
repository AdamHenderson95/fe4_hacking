
#ifndef PPU_H
#define PPU_H

#include <stdint.h>
#include <stdbool.h>

typedef struct Ppu Ppu;

// widescreen extension (fe4port)
#define PPU_WIDE_MAX 96
enum { PPU_WIDE_NORMAL = 0, PPU_WIDE_HIDE = 1, PPU_WIDE_VIRTUAL = 2 };
typedef struct PpuWideLine {
  bool enabled;        // draw the extension on this line (otherwise black)
  int innerFix;        // also redraw this many columns just inside each edge (for edge masks)
  bool ignoreWindows;  // ignore window masking in the redrawn area
  uint8_t layerMode[4];// per BG layer: normal tilemap / hidden outside 0..255 / virtual tiles
  int clipLo[4], clipHi[4]; // normal layers: outside 0..255 only show layer x in [lo, hi) (if hi > lo)
} PpuWideLine;
typedef void (*PpuWidePolicy)(Ppu* ppu, int line, PpuWideLine* out, void* ctx);
typedef uint16_t (*PpuWideTile)(Ppu* ppu, int layer, int px, int py, bool* opaque, void* ctx);

#include "snes.h"
#include "statehandler.h"

typedef struct BgLayer {
  uint16_t hScroll;
  uint16_t vScroll;
  bool tilemapWider;
  bool tilemapHigher;
  uint16_t tilemapAdr;
  uint16_t tileAdr;
  bool bigTiles;
  bool mosaicEnabled;
} BgLayer;

typedef struct Layer {
  bool mainScreenEnabled;
  bool subScreenEnabled;
  bool mainScreenWindowed;
  bool subScreenWindowed;
} Layer;

typedef struct WindowLayer {
  bool window1enabled;
  bool window2enabled;
  bool window1inversed;
  bool window2inversed;
  uint8_t maskLogic;
} WindowLayer;

struct Ppu {
  Snes* snes;
  // vram access
  uint16_t vram[0x8000];
  uint16_t vramPointer;
  bool vramIncrementOnHigh;
  uint16_t vramIncrement;
  uint8_t vramRemapMode;
  uint16_t vramReadBuffer;
  // cgram access
  uint16_t cgram[0x100];
  uint8_t cgramPointer;
  bool cgramSecondWrite;
  uint8_t cgramBuffer;
  // oam access
  uint16_t oam[0x100];
  uint8_t highOam[0x20];
  uint8_t oamAdr;
  uint8_t oamAdrWritten;
  bool oamInHigh;
  bool oamInHighWritten;
  bool oamSecondWrite;
  uint8_t oamBuffer;
  // object/sprites
  bool objPriority;
  uint16_t objTileAdr1;
  uint16_t objTileAdr2;
  uint8_t objSize;
  uint8_t objPixelBuffer[256]; // line buffers
  uint8_t objPriorityBuffer[256];
  bool timeOver;
  bool rangeOver;
  bool objInterlace;
  // background layers
  BgLayer bgLayer[4];
  uint8_t scrollPrev;
  uint8_t scrollPrev2;
  uint8_t mosaicSize;
  uint8_t mosaicStartLine;
  // layers
  Layer layer[5];
  // mode 7
  int16_t m7matrix[8]; // a, b, c, d, x, y, h, v
  uint8_t m7prev;
  bool m7largeField;
  bool m7charFill;
  bool m7xFlip;
  bool m7yFlip;
  bool m7extBg;
  // mode 7 internal
  int32_t m7startX;
  int32_t m7startY;
  // windows
  WindowLayer windowLayer[6];
  uint8_t window1left;
  uint8_t window1right;
  uint8_t window2left;
  uint8_t window2right;
  // color math
  uint8_t clipMode;
  uint8_t preventMathMode;
  bool addSubscreen;
  bool subtractColor;
  bool halfColor;
  bool mathEnabled[6];
  uint8_t fixedColorR;
  uint8_t fixedColorG;
  uint8_t fixedColorB;
  // settings
  bool forcedBlank;
  uint8_t brightness;
  uint8_t mode;
  bool bg3priority;
  bool evenFrame;
  bool pseudoHires;
  bool overscan;
  bool frameOverscan; // if we are overscanning this frame (determined at 0,225)
  bool interlace;
  bool frameInterlace; // if we are interlacing this frame (determined at start vblank)
  bool directColor;
  // latching
  uint16_t hCount;
  uint16_t vCount;
  bool hCountSecond;
  bool vCountSecond;
  bool countersLatched;
  uint8_t ppu1openBus;
  uint8_t ppu2openBus;
  // pixel buffer (xbgr)
  // times 2 for even and odd frame
  uint8_t pixelBuffer[512 * 4 * 239 * 2];
  // per-instance render caches (were file statics)
  uint32_t bright_now;
  int layerCache[4];
  uint16_t bg_pixel_buf[4];
  uint8_t bg_prio_buf[4];
  bool bg_window_state[6];
  bool skipRender;
  // widescreen extension: output (256 + 2*wideExt) x 239 pixels, 0x00RRGGBB
  int wideExt;
  uint32_t* wideBuf;
  PpuWidePolicy widePolicy;
  PpuWideTile wideTile;
  void* wideCtx;
  PpuWideLine wideLine;
  uint8_t objPixelW[256 + 2 * PPU_WIDE_MAX];
  uint8_t objPriorityW[256 + 2 * PPU_WIDE_MAX];
};

Ppu* ppu_init(Snes* snes);
void ppu_free(Ppu* ppu);
void ppu_reset(Ppu* ppu);
void ppu_handleState(Ppu* ppu, StateHandler* sh);
bool ppu_checkOverscan(Ppu* ppu);
void ppu_handleVblank(Ppu* ppu);
void ppu_handleFrameStart(Ppu* ppu);
void ppu_runLine(Ppu* ppu, int line);
extern void (*ppu_lineHook)(Ppu* ppu, int line);
uint8_t ppu_read(Ppu* ppu, uint8_t adr);
void ppu_write(Ppu* ppu, uint8_t adr, uint8_t val);
void ppu_latchHV(Ppu* ppu);
void ppu_putPixels(Ppu* ppu, uint8_t* pixels);

#endif
