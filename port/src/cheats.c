// Cheats: read and change the player's units in the game's RAM.
//
// Units (found for the port; see the project notes):
//   $7E:2180  directory: 8 words, offsets from $2180 to each army's unit list (army slot 0 = the player)
//   list      +0 army id, +1 ?, +2/+3 relations, +4 count, +5 handles (words, bank $7E)
//   handle    +0 type (0/2 named, 1 child, 3 generic), +1 ptr24 unit object, +4 ptr24 unit data, +7 ptr24 record+13 (ROM)
//   object    +0D current HP
//   data      +0 max HP, +1..+7 Str Mag Skl Spd Def Res Lck, +8 class, +9 level, +0A authority,
//             +0B gold (word, the game caps it at 50,000), +0D EXP
//   $056F     handle of the unit the cursor was last on
// Names: the record's name ID (record+15) indexes 16-byte slots at file 0x500000, text at +8.
#include <stdio.h>
#include <string.h>
#include "cheats.h"

static uint32_t w16(const uint8_t* r, uint32_t a) { return r[a] | r[a + 1] << 8; }

// RAM offset of a 24-bit pointer in banks $7E/$7F, or 0 if it isn't one
static uint32_t ram_ptr(const uint8_t* r, uint32_t a) {
  uint8_t bank = r[a + 2];
  if(bank != 0x7E && bank != 0x7F) return 0;
  return (uint32_t)(bank - 0x7E) * 0x10000 + w16(r, a);
}

static int handle_ok(const uint8_t* r, uint32_t h) {
  if(h < 0x2000 || h > 0xFFE0) return 0;
  uint8_t t = r[h];
  if(t > 3) return 0;
  uint32_t o = ram_ptr(r, h + 1), d = ram_ptr(r, h + 4);
  if(!o || o + 0x20 > 0x20000) return 0;
  if(t != 3 && (!d || d + 0x10 > 0x20000)) return 0;
  return 1;
}

static void decode_name(const uint8_t* rom, int romLen, uint32_t nid, char* out, int n) {
  out[0] = 0;
  uint32_t a = 0x500000 + 16 * nid + 8;
  if(nid > 575 || a + 8 > (uint32_t)romLen) return;
  int k = 0;
  for(int i = 0; i < 8 && k < n - 1; i++) {
    uint8_t b = rom[a + i]; char c;
    if(b == 0x00 || b == 0x01) break;
    if(b >= 0x10 && b <= 0x29) c = 'A' + b - 0x10;
    else if(b >= 0x2A && b <= 0x43) c = 'a' + b - 0x2A;
    else if(b == 0xBF) c = ' ';
    else if(b == 0x48) c = '\'';
    else if(b == 0x49) c = '-';
    else break;
    out[k++] = c;
  }
  out[k] = 0;
  while(k && out[k - 1] == ' ') out[--k] = 0;
}

static int unit_info(const uint8_t* r, const uint8_t* rom, int romLen, uint32_t h, CheatUnit* u) {
  memset(u, 0, sizeof *u);
  if(!handle_ok(r, h) || r[h] == 3) return 0;
  uint32_t o = ram_ptr(r, h + 1), d = ram_ptr(r, h + 4);
  u->handle = h;
  u->hp = r[o + 0x0D]; u->maxHp = r[d];
  u->level = r[d + 9]; u->exp = r[d + 0x0D]; u->gold = w16(r, d + 0x0B);
  // name through the record in ROM (types 0 and 2; children use their own record layout)
  uint32_t rp = (uint32_t)((r[h + 9] & 0x3F) << 16 | w16(r, h + 7));
  if(r[h + 9] >= 0x80 && r[h + 9] < 0xC0 && rp + 4 < (uint32_t)romLen && r[h] != 1)
    decode_name(rom, romLen, rom[rp + 2] | rom[rp + 3] << 8, u->name, sizeof u->name);
  if(!u->name[0]) snprintf(u->name, sizeof u->name, "Unit");
  return u->maxHp > 0 && u->maxHp < 100 && u->level > 0 && u->level <= 40;
}

int cheat_army(const uint8_t* r, const uint8_t* rom, int romLen, CheatUnit* out, int max) {
  uint32_t list = 0x2180 + w16(r, 0x2180);
  if(list + 5 > 0x2400) return 0;
  int cnt = r[list + 4], n = 0;
  if(cnt > 64) return 0;
  for(int i = 0; i < cnt && n < max; i++) {
    uint32_t h = w16(r, list + 5 + 2 * i);
    if(unit_info(r, rom, romLen, h, &out[n])) n++;
  }
  return n;
}

int cheat_selected(const uint8_t* r, const uint8_t* rom, int romLen, CheatUnit* u) {
  // only units of the player's army
  CheatUnit army[64]; int n = cheat_army(r, rom, romLen, army, 64);
  uint32_t h = w16(r, 0x056F);
  for(int i = 0; i < n; i++) if(army[i].handle == h) { *u = army[i]; return 1; }
  return 0;
}

static void apply_one(uint8_t* r, uint32_t h, int what) {
  uint32_t o = ram_ptr(r, h + 1), d = ram_ptr(r, h + 4);
  if(!o || !d) return;
  switch(what) {
    case CHEAT_HEAL: r[o + 0x0D] = r[d]; break;
    case CHEAT_GOLD: r[d + 0x0B] = 50000 & 0xff; r[d + 0x0C] = 50000 >> 8; break;
    case CHEAT_EXP: if(r[d + 0x0D] < 99) r[d + 0x0D] = 99; break;
  }
}

int cheat_apply(uint8_t* r, const uint8_t* rom, int romLen, int what, int allUnits) {
  CheatUnit army[64]; int n = cheat_army(r, rom, romLen, army, 64), done = 0;
  uint32_t sel = w16(r, 0x056F);
  for(int i = 0; i < n; i++) if(allUnits || army[i].handle == sel) { apply_one(r, army[i].handle, what); done++; }
  return done;
}
