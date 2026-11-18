// Love tracker (port 0.15).  Where FE4 keeps love points:
//
//   $7E:2180    army directory; the player's list: +4 count, +5 unit handles (words, bank $7E)
//   handle      +1 ptr24 unit object, +7 ptr24 personal record (ROM record+13 for named units, a RAM
//               block for the generation-2 children), +$10 ptr24 love block (women only, else 0)
//   record      +2 name ID, +4 army slot (bit 7 = no love slot); men are slots 1-15, women 16 and up
//   love block  one word per man: word k = the man in army slot k+1; low 9 bits $1FF = never
//   object      +0 flags ($0200 = gone), +3 partner's army slot once married
// Love is added by $87:AE05 (woman = unit $056F, man's slot in A) and caps at 500, which marries the
// couple ($84:8C31 writes each one's slot into the other's object +3).
#include <stdio.h>
#include <string.h>
#include "love.h"
#include "cheats.h"

static int w16(const uint8_t* r, uint32_t a) { return r[a] | r[a + 1] << 8; }

static int32_t ram_ptr(const uint8_t* r, uint32_t a) {
  uint8_t b = r[a + 2];
  if(b != 0x7E && b != 0x7F) return -1;
  int32_t o = (b - 0x7E) * 0x10000 + w16(r, a);
  return o + 0x40 <= 0x20000 ? o : -1;
}

static int32_t rom_off(uint8_t bank, int addr, int romLen) {
  int32_t o;
  if(bank >= 0xC0) o = (bank - 0xC0) << 16 | addr;
  else if(bank >= 0x80 && addr >= 0x8000) o = (bank - 0x80) << 16 | addr;
  else if(bank >= 0x40 && bank < 0x7E) o = 0x400000 | (bank - 0x40) << 16 | addr;
  else return -1;
  return o + 8 <= romLen ? o : -1;
}

// name ID and army slot of a handle's unit; 0 if it can't be read
static int person(const uint8_t* r, const uint8_t* rom, int romLen, uint32_t h, int* nid, int* slot) {
  uint8_t b = r[h + 9];
  int a = w16(r, h + 7);
  if(b == 0x7E || b == 0x7F) {              // a child's block in RAM
    int32_t p = ram_ptr(r, h + 7);
    if(p < 0) return 0;
    *nid = w16(r, p + 2); *slot = r[p + 4];
  } else {
    int32_t p = rom_off(b, a, romLen);
    if(p < 0) return 0;
    *nid = rom[p + 2] | rom[p + 3] << 8; *slot = rom[p + 4];
  }
  return 1;
}

void love_read(const uint8_t* r, const uint8_t* rom, int romLen, LoveInfo* li) {
  memset(li, 0, sizeof *li);
  li->chapter = r[0x0D6A];
  if(li->chapter > 11) return;
  uint32_t list = 0x2180 + w16(r, 0x2180);
  if(list + 5 > 0x2400) return;
  int cnt = r[list + 4];
  if(cnt > 64) return;
  for(int i = 0; i < cnt; i++) {
    uint32_t h = w16(r, list + 5 + 2 * i);
    if(h < 0x2000 || h > 0xFFC0 || r[h] > 2) continue;      // named units and children only
    int32_t obj = ram_ptr(r, h + 1);
    if(obj < 0 || (w16(r, obj) & 0x0200)) continue;        // gone
    int nid, slot;
    if(!person(r, rom, romLen, h, &nid, &slot) || (slot & 0x80)) continue;
    char name[16]; cheat_name(rom, romLen, nid, name, sizeof name);
    if(!name[0]) snprintf(name, sizeof name, "#%d", slot);
    int32_t lb = ram_ptr(r, h + 0x10);
    if(slot >= 1 && slot < LOVE_SLOTS && lb < 0) {
      if(li->nMen < LOVE_SLOTS) { li->men[li->nMen].slot = slot; snprintf(li->men[li->nMen].name, 16, "%s", name); li->nMen++; }
    } else if(slot >= LOVE_SLOTS && lb >= 0 && li->nWomen < 24) {
      LoveWoman* w = &li->women[li->nWomen++];
      w->slot = slot; snprintf(w->name, 16, "%s", name);
      int p = r[obj + 3];
      w->partner = p ? p : -1;
      w->love[0] = -1;
      for(int k = 1; k < LOVE_SLOTS; k++) {
        int v = w16(r, lb + 2 * (k - 1));
        w->love[k] = (v & 0x1FF) == 0x1FF ? -1 : (v > LOVE_MAX ? LOVE_MAX : v);
      }
    }
  }
  li->ok = li->nWomen > 0;
}

const char* love_man_name(const LoveInfo* li, int slot) {
  for(int i = 0; i < li->nMen; i++) if(li->men[i].slot == slot) return li->men[i].name;
  return NULL;
}

int love_gains(const LoveInfo* a, const LoveInfo* b, LoveGain* out, int max) {
  if(!a->ok || !b->ok || a->chapter != b->chapter) return 0;
  int n = 0, pairs = 0;
  for(int i = 0; i < b->nWomen; i++) {
    const LoveWoman* w = &b->women[i];
    const LoveWoman* v = NULL;
    for(int j = 0; j < a->nWomen; j++) if(a->women[j].slot == w->slot) v = &a->women[j];
    if(!v) continue;
    for(int k = 1; k < LOVE_SLOTS; k++) {
      if(w->love[k] < 0 || v->love[k] < 0 || w->love[k] <= v->love[k]) continue;
      const char* m = love_man_name(b, k);
      if(!m) continue;
      pairs++;
      if(n < max) {
        LoveGain* g = &out[n++];
        snprintf(g->man, 16, "%s", m); snprintf(g->woman, 16, "%s", w->name);
        g->gain = w->love[k] - v->love[k]; g->total = w->love[k];
      }
    }
  }
  return n;
}
