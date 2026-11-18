// Love tracker: every couple's love points, read live from the game's RAM (port 0.15).
#ifndef FE4_LOVE_H
#define FE4_LOVE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define LOVE_MAX 500        // a couple marries at 500
#define LOVE_SLOTS 16       // men are army slots 1-15

typedef struct LoveMan { int slot; char name[16]; } LoveMan;

typedef struct LoveWoman {
  int slot;                // army slot (16 and up)
  char name[16];
  int partner;             // army slot of her husband, or -1
  int love[LOVE_SLOTS];    // by the man's army slot; -1 = they can never fall in love
} LoveWoman;

typedef struct LoveInfo {
  int ok;                  // a chapter is on and the army has at least one woman with love points
  int chapter;
  int nMen, nWomen;
  LoveMan men[LOVE_SLOTS];
  LoveWoman women[24];
} LoveInfo;

// one couple whose love went up
typedef struct LoveGain { char man[16], woman[16]; int gain, total; } LoveGain;

void love_read(const uint8_t* ram, const uint8_t* rom, int romLen, LoveInfo* out);
const char* love_man_name(const LoveInfo* li, int slot);     // NULL if he isn't in the army
// couples whose love went up between two readings of the same game (returns how many; none when the
// game changed under them: another chapter, a loaded state or save)
int love_gains(const LoveInfo* before, const LoveInfo* now, LoveGain* out, int max);

#ifdef __cplusplus
}
#endif
#endif
