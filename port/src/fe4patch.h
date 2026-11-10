// Byte patches applied to the ROM image before translation. Each patch checks the original bytes
// first, so a ROM that differs there (a hack that changed the same code) is left alone.
#ifndef FE4PATCH_H
#define FE4PATCH_H
#include <stdint.h>
#include <string.h>

typedef struct { uint32_t off, olen, nlen; const unsigned char* orig; const unsigned char* data; } Fe4Patch;

// returns 1 if every patch in the list applied (or the ROM already has exactly these changes, e.g. a hack
// built with them), 0 if any original bytes didn't match (nothing changed then)
static inline int fe4patch_apply(uint8_t* rom, int len, const Fe4Patch* list) {
  int already = 1;
  for(const Fe4Patch* p = list; p->olen; p++) {
    if(p->off + p->nlen > (uint32_t)len) return 0;
    // a flag word at the start of the new code may differ (it's the on/off switch): skip 2 bytes there
    int skip = p->nlen > 16 ? 2 : 0;
    if(memcmp(rom + p->off + skip, p->data + skip, p->nlen - skip)) already = 0;
  }
  if(already) return 1;
  for(const Fe4Patch* p = list; p->olen; p++)
    if(memcmp(rom + p->off, p->orig, p->olen)) return 0;
  for(const Fe4Patch* p = list; p->olen; p++) memcpy(rom + p->off, p->data, p->nlen);
  return 1;
}
#endif
