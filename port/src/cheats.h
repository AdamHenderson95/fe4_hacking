// Cheats on the player's units (game RAM). See cheats.c for the layout.
#ifndef FE4_CHEATS_H
#define FE4_CHEATS_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct CheatUnit {
  uint32_t handle;
  char name[16];
  int hp, maxHp, level, exp, gold;
} CheatUnit;

enum { CHEAT_HEAL = 1, CHEAT_GOLD = 2, CHEAT_EXP = 3 };

int cheat_army(const uint8_t* ram, const uint8_t* rom, int romLen, CheatUnit* out, int max); // the player's units
int cheat_selected(const uint8_t* ram, const uint8_t* rom, int romLen, CheatUnit* u);        // the unit the cursor was last on (player's)
int cheat_apply(uint8_t* ram, const uint8_t* rom, int romLen, int what, int allUnits);       // returns how many units changed

#ifdef __cplusplus
}
#endif
#endif
