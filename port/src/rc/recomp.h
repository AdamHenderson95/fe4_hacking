#ifndef RECOMP_H
#define RECOMP_H
#include <stdio.h>
#include <stdint.h>
typedef struct { uint32_t pc; uint32_t fs; } RcGenEntry;
typedef struct { int blocks, instrs; } RcGenStats;
// rom: headerless image; entries: block entry points; follow: also translate static branch/call targets
RcGenStats rc_generate(const uint8_t* rom, int romSize, const RcGenEntry* entries, int n, int follow, FILE* out);
#endif
