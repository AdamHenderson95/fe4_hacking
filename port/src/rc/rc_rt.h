#ifndef RC_RT_H
#define RC_RT_H
#include "snes.h"
#include "rc_gen.h"

typedef struct RcStats { unsigned long long blocks, interp, special; } RcStats;
extern RcStats rc_stats;
extern int rc_recordMisses;

void rc_setBlocks(const RcEntry* tab, int n);
int rc_blockCount(void);
void rc_runFrame(Snes* snes);
void rc_stepOnce(Snes* snes);
int rc_saveCoverage(const char* path, int append);
void rc_clearCoverage(void);
#endif
