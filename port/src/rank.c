// Rank tracker (port 0.14).  FE4 ranks a finished game on four things; the game keeps them in RAM:
//
//   Tactics     turns: chapter c's turns are saved at $0D93 + 2c when it is cleared ($81:B2D1), the
//               current chapter's turn is $0D8F (FFFF after a clear); each castle an enemy takes
//               ($0D73, counted at $84:CE89) lowers the grade one step.  Grade code $84:8CFE.
//   Experience  level-ups of the whole army: $7E:3D83, +1 at $84:AADB.  Grade code $84:8D97 (more than
//               1,440 falls through to E, as in the game).
//   Combat      battle losses: $7E:7358 + character (48 bytes, +1 at $91:EB27).  Grade code $84:8D65.
//   Survival    units alive at the end of each generation ($7E:3D85, added at the end of chapters 5
//               and 11 by $81:B2BC); not knowable before then.
//
// The grade tables are read from the ROM (5 ranges, A to E: low, high), so a hack that changes them
// is shown right; $84:8ED7 picks the first range a value fits, else E.
#include <string.h>
#include "rank.h"

static int w16(const uint8_t* p, uint32_t a) { return p[a] | p[a + 1] << 8; }

// file offsets (bank $84 = file $04xxxx) of the tables and the code that names them
static const struct { uint32_t code; uint8_t ldy[3]; uint32_t table; int fallback[4][2]; } TABLES[RANK_COUNT] = {
  { 0x048D18, { 0xA0, 0x2F, 0x8D }, 0x048D2F, { { 1, 399 }, { 400, 549 }, { 550, 799 }, { 800, 1099 } } },
  { 0x048DA7, { 0xA0, 0xB1, 0x8D }, 0x048DB1, { { 1000, 1440 }, { 800, 999 }, { 600, 799 }, { 400, 599 } } },
  { 0x048D80, { 0xA0, 0x8B, 0x8D }, 0x048D8B, { { 0, 3 }, { 4, 10 }, { 11, 30 }, { 31, 50 } } },
};

static int grade(int v, const int t[5][2]) {
  for(int x = 0; x < 4; x++) {
    int lo = t[x][0], hi = t[x][1];
    if((int16_t)(lo - 1 - v) >= 0) continue;      // DEC / CMP / BPL
    if(hi >= v) return x;                          // CMP / BCS
  }
  return 4;
}

void rank_read(const uint8_t* ram, const uint8_t* rom, int romLen, RankInfo* r) {
  memset(r, 0, sizeof *r);
  for(int k = 0; k < RANK_COUNT; k++) {
    int fromRom = romLen > (int)TABLES[k].table + 16 && !memcmp(rom + TABLES[k].code, TABLES[k].ldy, 3);
    for(int x = 0; x < 4; x++)
      for(int j = 0; j < 2; j++)
        r->limit[k][x][j] = fromRom ? w16(rom, TABLES[k].table + 4 * x + 2 * j) : TABLES[k].fallback[x][j];
    // E: anything past D
    r->limit[k][4][0] = k == RANK_EXPERIENCE ? 0 : r->limit[k][3][1] + 1;
    r->limit[k][4][1] = k == RANK_EXPERIENCE ? r->limit[k][3][0] - 1 : -1;
  }
  r->chapter = ram[0x0D6A];
  int sum = 0;
  for(int c = 0; c < 12; c++) { int t = w16(ram, 0x0D93 + 2 * c); if(t != 0xFFFF && t < 10000) sum += t; }
  int now = w16(ram, 0x0D8F);
  r->turnsThis = now == 0xFFFF || now > 9999 ? 0 : now;
  r->turns = sum + r->turnsThis;
  r->castlesLost = w16(ram, 0x0D73) & 0xFF;
  r->levelUps = w16(ram, 0x3D83);
  for(int i = 0; i < 48; i++) r->deaths += ram[0x7358 + i];
  r->gen1Survivors = w16(ram, 0x3D85);
  r->inGame = r->chapter <= 11 && (r->turnsThis > 0 || sum > 0);
  int t = grade(r->turns, (const int(*)[2])r->limit[RANK_TACTICS]) + r->castlesLost;
  r->grade[RANK_TACTICS] = t > 4 ? 4 : t;
  r->grade[RANK_EXPERIENCE] = grade(r->levelUps, (const int(*)[2])r->limit[RANK_EXPERIENCE]);
  r->grade[RANK_COMBAT] = grade(r->deaths, (const int(*)[2])r->limit[RANK_COMBAT]);
}
