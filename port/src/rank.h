// Rank tracker: the numbers FE4's end-of-game ranking is based on, read live from the game's RAM.
#ifndef FE4_RANK_H
#define FE4_RANK_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { RANK_TACTICS, RANK_EXPERIENCE, RANK_COMBAT, RANK_COUNT };

typedef struct RankInfo {
  int inGame;          // a chapter has started (turn 1 or later, or a chapter already cleared)
  int chapter;         // 0 = Prologue ... 11 = Final Chapter
  int turns;           // all chapters so far, this one included
  int turnsThis;       // this chapter's turn
  int castlesLost;     // castles of yours an enemy took (each lowers Tactics one grade)
  int levelUps;        // level-ups of the whole army (Experience)
  int deaths;          // your units defeated in battle (Combat; not the arena)
  int gen1Survivors;   // counted when the Prologue-chapter 5 part ends (0 before)
  int grade[RANK_COUNT];        // 0 = A ... 4 = E, if the game ended now
  int limit[RANK_COUNT][5][2];  // each grade's range (from the game's own tables)
} RankInfo;

void rank_read(const uint8_t* ram, const uint8_t* rom, int romLen, RankInfo* r);

#ifdef __cplusplus
}
#endif
#endif
