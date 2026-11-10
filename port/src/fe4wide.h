#ifndef FE4WIDE_H
#define FE4WIDE_H
#include <stdint.h>
#include "snes.h"

#define FE4WIDE_EXT 72                       // pixels added on each side: 400x224 picture
#define FE4WIDE_W (256 + 2 * FE4WIDE_EXT)

// apply the ROM changes widescreen needs (returns how many were applied)
int fe4wide_patchRom(uint8_t* rom, int len);              // 1 = applied (unit window follows the flag, set to on)
void fe4wide_setRomFlag(uint8_t* rom, int len, int on);  // widescreen unit window on/off (write to the running ROM copy)
// render the extension into buf (FE4WIDE_W x 239 pixels)
void fe4wide_attach(Snes* snes, uint32_t* buf);
extern int fe4wide_selftest;
#endif
