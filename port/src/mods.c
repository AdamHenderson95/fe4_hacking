// Mods: .ips / .bps patches in the mods folder, applied to the ROM at startup in load order.
// The order and on/off state live in mods/load_order.txt ("on<TAB>file" / "off<TAB>file").
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#define strcasecmp _stricmp
#else
#include <dirent.h>
#include <strings.h>
#define MKDIR(p) mkdir(p, 0755)
#endif
#include "mods.h"

#define MAXMODS 256
static ModInfo mods[MAXMODS];
static int nmods;
static char dir[1024];
static char appliedSet[MAXMODS][256]; static int nApplied; // what this session applied, in order
static char startSet[MAXMODS][256]; static int nStart;     // what was switched on when the session started

const char* mods_dir(void) { return dir; }
int mods_count(void) { return nmods; }
ModInfo* mods_at(int i) { return i >= 0 && i < nmods ? &mods[i] : NULL; }
int mods_applied(void) { return nApplied; }

static int is_mod_file(const char* name) {
  const char* e = strrchr(name, '.');
  return e && (!strcasecmp(e, ".ips") || !strcasecmp(e, ".bps"));
}
static int is_rando(const char* name) { return !strncmp(name, "Randomizer ", 11); }
static int find(const char* name) { for(int i = 0; i < nmods; i++) if(!strcmp(mods[i].file, name)) return i; return -1; }

static int add(const char* name, int on) {
  if(nmods >= MAXMODS || find(name) >= 0) return -1;
  ModInfo* m = &mods[nmods]; memset(m, 0, sizeof *m);
  snprintf(m->file, sizeof m->file, "%s", name);
  m->enabled = on; m->randomizer = is_rando(name);
  return nmods++;
}

static int file_exists(const char* name) {
  char p[1400]; snprintf(p, sizeof p, "%s%s", dir, name);
  struct stat st; return stat(p, &st) == 0;
}

// files in the folder, sorted by name
static int list_files(char names[][256], int max) {
  int n = 0;
#ifdef _WIN32
  char pat[1100]; snprintf(pat, sizeof pat, "%s*.*", dir);
  WIN32_FIND_DATAA fd; HANDLE h = FindFirstFileA(pat, &fd);
  if(h != INVALID_HANDLE_VALUE) {
    do { if(!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && is_mod_file(fd.cFileName) && n < max) snprintf(names[n++], 256, "%s", fd.cFileName); }
    while(FindNextFileA(h, &fd));
    FindClose(h);
  }
#else
  DIR* d = opendir(dir);
  if(d) { struct dirent* e; while((e = readdir(d))) if(is_mod_file(e->d_name) && n < max) snprintf(names[n++], 256, "%s", e->d_name); closedir(d); }
#endif
  for(int i = 1; i < n; i++) for(int j = i; j > 0 && strcasecmp(names[j - 1], names[j]) > 0; j--) {
    char t[256]; memcpy(t, names[j], 256); memcpy(names[j], names[j - 1], 256); memcpy(names[j - 1], t, 256);
  }
  return n;
}

void mods_rescan(void) {
  // drop entries whose file is gone
  int w = 0;
  for(int i = 0; i < nmods; i++) if(file_exists(mods[i].file)) mods[w++] = mods[i];
  nmods = w;
  // new files go to the end, switched on (a new randomizer seed only if no other seed is on)
  static char names[MAXMODS][256];
  int n = list_files(names, MAXMODS);
  for(int i = 0; i < n; i++) if(find(names[i]) < 0) {
    int on = 1;
    if(is_rando(names[i])) for(int k = 0; k < nmods; k++) if(mods[k].randomizer && mods[k].enabled) on = 0;
    add(names[i], on);
  }
}

void mods_init(const char* d) {
  snprintf(dir, sizeof dir, "%s", d);
  MKDIR(dir);
  nmods = 0;
  char p[1100]; snprintf(p, sizeof p, "%sload_order.txt", dir);
  FILE* f = fopen(p, "r");
  if(f) {
    char line[400];
    while(fgets(line, sizeof line, f)) {
      line[strcspn(line, "\r\n")] = 0;
      if(line[0] == '#' || !line[0]) continue;
      char* tab = strchr(line, '\t'); if(!tab) continue;
      *tab = 0;
      if(file_exists(tab + 1)) add(tab + 1, !strcmp(line, "on"));
    }
    fclose(f);
  }
  mods_rescan();
  mods_save();
}

void mods_save(void) {
  char p[1100]; snprintf(p, sizeof p, "%sload_order.txt", dir);
  FILE* f = fopen(p, "w"); if(!f) return;
  fprintf(f, "# Mods load order: patches are applied top to bottom. on/off, a tab, then the file name.\n"
             "# The port keeps this file up to date; you can also change it in the F1 menu (Mods).\n");
  for(int i = 0; i < nmods; i++) fprintf(f, "%s\t%s\n", mods[i].enabled ? "on" : "off", mods[i].file);
  fclose(f);
}

void mods_move(int i, int delta) {
  int j = i + delta;
  if(i < 0 || j < 0 || i >= nmods || j >= nmods) return;
  ModInfo t = mods[i]; mods[i] = mods[j]; mods[j] = t;
}

void mods_set(int i, int on) {
  if(i < 0 || i >= nmods) return;
  mods[i].enabled = on;
  if(on && mods[i].randomizer) for(int k = 0; k < nmods; k++) if(k != i && mods[k].randomizer) mods[k].enabled = 0;
}

int mods_add_first_run(const char* file, int on) {
  int i = find(file);
  if(i < 0) i = add(file, 0);
  if(i < 0) return -1;
  // a new randomizer seed goes last (it was made from the ROM with the other mods applied)
  while(i < nmods - 1) { mods_move(i, 1); i++; }
  mods_set(i, on);
  return i;
}

int mods_changed(void) {
  int k = 0;
  for(int i = 0; i < nmods; i++) if(mods[i].enabled) {
    if(k >= nStart || strcmp(startSet[k], mods[i].file)) return 1;
    k++;
  }
  return k != nStart;
}

uint32_t mods_set_hash(void) {
  if(!nApplied) return 0;
  uint32_t h = 2166136261u;
  for(int i = 0; i < nApplied; i++) { for(const char* s = appliedSet[i]; *s; s++) h = (h ^ (uint8_t)tolower(*s)) * 16777619u; h = (h ^ '|') * 16777619u; }
  return h ? h : 1;
}

// ---------------- patch formats ----------------
static uint8_t* read_all(const char* path, int* n) {
  FILE* f = fopen(path, "rb"); if(!f) return NULL;
  fseek(f, 0, SEEK_END); long len = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t* d = malloc(len + 1);
  if(fread(d, 1, len, f) != (size_t)len) { fclose(f); free(d); return NULL; }
  fclose(f); *n = (int)len; return d;
}

// IPS onto buf (len may grow, up to cap); returns 1 ok, 0 malformed
static int ips_apply(const uint8_t* p, int pn, uint8_t** buf, int* len) {
  if(pn < 8 || memcmp(p, "PATCH", 5)) return 0;
  int i = 5;
  while(i + 3 <= pn) {
    if(!memcmp(p + i, "EOF", 3)) {
      if(i + 6 <= pn) { int t = (p[i + 3] << 16) | (p[i + 4] << 8) | p[i + 5]; if(t < *len) *len = t; } // truncation extension
      return 1;
    }
    if(i + 5 > pn) return 0;
    int off = (p[i] << 16) | (p[i + 1] << 8) | p[i + 2]; int sz = (p[i + 3] << 8) | p[i + 4]; i += 5;
    int rle = 0, val = 0;
    if(!sz) { if(i + 3 > pn) return 0; rle = 1; sz = (p[i] << 8) | p[i + 1]; val = p[i + 2]; i += 3; }
    else if(i + sz > pn) return 0;
    if(off + sz > *len) {
      if(off + sz > 0x1000000) return 0;
      *buf = realloc(*buf, off + sz); memset(*buf + *len, 0, off + sz - *len); *len = off + sz;
    }
    if(rle) memset(*buf + off, val, sz); else { memcpy(*buf + off, p + i, sz); i += sz; }
  }
  return 0; // no EOF marker
}

static uint32_t crc32(const uint8_t* d, int n) {
  static uint32_t t[256]; static int init;
  if(!init) { for(uint32_t i = 0; i < 256; i++) { uint32_t c = i; for(int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1; t[i] = c; } init = 1; }
  uint32_t c = 0xFFFFFFFFu;
  for(int i = 0; i < n; i++) c = t[(c ^ d[i]) & 0xff] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}
static uint64_t bps_num(const uint8_t* p, int pn, int* i) {
  uint64_t v = 0, s = 1;
  while(*i < pn) { uint8_t x = p[(*i)++]; v += (x & 0x7f) * s; if(x & 0x80) return v; s <<= 7; v += s; }
  return v;
}
// BPS: returns new buffer (caller frees) or NULL; *why explains a failure
static uint8_t* bps_apply(const uint8_t* p, int pn, const uint8_t* src, int sn, int* outLen, const char** why) {
  *why = "not a valid .bps file";
  if(pn < 16 || memcmp(p, "BPS1", 4)) return NULL;
  uint32_t srcCrc = p[pn - 12] | (p[pn - 11] << 8) | (p[pn - 10] << 16) | ((uint32_t)p[pn - 9] << 24);
  uint32_t dstCrc = p[pn - 8] | (p[pn - 7] << 8) | (p[pn - 6] << 16) | ((uint32_t)p[pn - 5] << 24);
  uint32_t patCrc = p[pn - 4] | (p[pn - 3] << 8) | (p[pn - 2] << 16) | ((uint32_t)p[pn - 1] << 24);
  if(crc32(p, pn - 4) != patCrc) { *why = "the .bps file is damaged (checksum)"; return NULL; }
  int i = 4;
  uint64_t ss = bps_num(p, pn, &i), ts = bps_num(p, pn, &i), ms = bps_num(p, pn, &i);
  i += (int)ms;
  if((int)ss != sn || crc32(src, sn) != srcCrc) { *why = "made for a different ROM (or needs other mods before it)"; return NULL; }
  if(ts > 0x1000000) return NULL;
  uint8_t* out = calloc(1, ts ? ts : 1);
  uint64_t o = 0; int64_t srcRel = 0, dstRel = 0;
  int end = pn - 12;
  while(i < end) {
    uint64_t d = bps_num(p, pn, &i); uint64_t len = (d >> 2) + 1; int act = d & 3;
    if(o + len > ts) { free(out); return NULL; }
    if(act == 0) { for(uint64_t k = 0; k < len; k++, o++) out[o] = o < (uint64_t)sn ? src[o] : 0; }
    else if(act == 1) { if(i + (int)len > end) { free(out); return NULL; } memcpy(out + o, p + i, len); i += (int)len; o += len; }
    else {
      uint64_t v = bps_num(p, pn, &i); int64_t off = (v & 1 ? -1 : 1) * (int64_t)(v >> 1);
      if(act == 2) { srcRel += off; for(uint64_t k = 0; k < len; k++) { if(srcRel < 0 || srcRel >= sn) { free(out); return NULL; } out[o++] = src[srcRel++]; } }
      else { dstRel += off; for(uint64_t k = 0; k < len; k++) { if(dstRel < 0 || dstRel >= (int64_t)o) { free(out); return NULL; } out[o++] = out[dstRel++]; } }
    }
  }
  if(crc32(out, (int)ts) != dstCrc) { *why = "the result didn't match the patch's checksum"; free(out); return NULL; }
  *outLen = (int)ts; return out;
}

// SNES header checksum check for FE4's ExHiROM layout (header at $40FFC0)
static int checksum_ok(const uint8_t* r, int n) {
  if(n < 0x410000) return 0;
  uint32_t s = 0; for(int i = 0; i < n; i++) s += r[i];
  uint16_t want = r[0x40FFDE] | (r[0x40FFDF] << 8), comp = r[0x40FFDC] | (r[0x40FFDD] << 8);
  return (uint16_t)s == want && (uint16_t)(want ^ comp) == 0xFFFF;
}
static int fe4_header(const uint8_t* r, int n) { return n >= 0x410000 && !memcmp(r + 0x40FFC0, "FIREEMBLEM4", 11); }

// apply one patch; returns 1 ok
static int apply_one(ModInfo* m, uint8_t** rom, int* len, const uint8_t* hdr, int hadHdr) {
  char p[1400]; snprintf(p, sizeof p, "%s%s", dir, m->file);
  int pn; uint8_t* pd = read_all(p, &pn);
  m->note[0] = 0;
  if(!pd) { snprintf(m->note, sizeof m->note, "couldn't read the file"); return 0; }
  const char* e = strrchr(m->file, '.');
  int ok = 0;
  if(e && !strcasecmp(e, ".bps")) {
    const char* why = ""; int on = 0;
    uint8_t* out = bps_apply(pd, pn, *rom, *len, &on, &why);
    if(!out && hadHdr) { // made for the file with its copier header
      uint8_t* tmp = malloc(*len + 512); memcpy(tmp, hdr, 512); memcpy(tmp + 512, *rom, *len);
      const char* why2; out = bps_apply(pd, pn, tmp, *len + 512, &on, &why2); free(tmp);
    }
    if(out) {
      if((on & 0x7fff) == 0x200) { memmove(out, out + 512, on - 512); on -= 512; }
      if(fe4_header(out, on)) { free(*rom); *rom = out; *len = on; ok = 1; }
      else { free(out); snprintf(m->note, sizeof m->note, "the patched ROM isn't FE4 any more"); }
    } else snprintf(m->note, sizeof m->note, "%s", why);
  } else {
    // try the patch both on the headerless image and on the image with a copier header, and keep the
    // one whose SNES checksum comes out right (fe4kit fixes the checksum); otherwise the form of the user's file
    uint8_t* a = malloc(*len); memcpy(a, *rom, *len); int an = *len;
    int aok = ips_apply(pd, pn, &a, &an);
    uint8_t* b = malloc(*len + 512); memcpy(b, hdr, 512); memcpy(b + 512, *rom, *len); int bn = *len + 512;
    int bok = ips_apply(pd, pn, &b, &bn);
    if(bok && bn >= 512) { memmove(b, b + 512, bn - 512); bn -= 512; }
    int aGood = aok && fe4_header(a, an), bGood = bok && fe4_header(b, bn);
    int pick = 0; // 1 = a, 2 = b
    if(aGood && checksum_ok(a, an)) pick = 1;
    else if(bGood && checksum_ok(b, bn)) pick = 2;
    else if(hadHdr ? bGood : aGood) pick = hadHdr ? 2 : 1;
    else if(aGood) pick = 1; else if(bGood) pick = 2;
    if(!aok && !bok) snprintf(m->note, sizeof m->note, "not a valid .ips file");
    else if(!pick) snprintf(m->note, sizeof m->note, "the patched ROM isn't FE4 any more");
    else {
      if(pick == 2 && !hadHdr) snprintf(m->note, sizeof m->note, "made for a ROM with a copier header (adjusted)");
      if(pick == 1 && hadHdr) snprintf(m->note, sizeof m->note, "made for a ROM without a copier header (adjusted)");
      free(*rom);
      if(pick == 1) { *rom = a; *len = an; a = NULL; } else { *rom = b; *len = bn; b = NULL; }
      ok = 1;
    }
    free(a); free(b);
  }
  free(pd);
  return ok;
}

int mods_apply_to(uint8_t** rom, int* len, const uint8_t* hdr, int hadHdr, int skipRandomizer) {
  static const uint8_t zero[512];
  if(!hdr) hdr = zero;
  int n = 0;
  for(int i = 0; i < nmods; i++) {
    if(!mods[i].enabled || (skipRandomizer && mods[i].randomizer)) continue;
    ModInfo tmp = mods[i];
    if(apply_one(&tmp, rom, len, hdr, hadHdr)) n++; else return -1;
  }
  return n;
}

int mods_apply(uint8_t** rom, int* len, const uint8_t* hdr, int hadHdr) {
  static const uint8_t zero[512];
  if(!hdr) hdr = zero;
  nApplied = nStart = 0;
  for(int i = 0; i < nmods; i++) {
    ModInfo* m = &mods[i];
    m->state = 0;
    if(!m->enabled) continue;
    snprintf(startSet[nStart++], 256, "%s", m->file);
    if(apply_one(m, rom, len, hdr, hadHdr)) { m->state = 1; snprintf(appliedSet[nApplied++], 256, "%s", m->file); printf("mod: %s%s%s\n", m->file, m->note[0] ? " - " : "", m->note); }
    else { m->state = -1; printf("mod FAILED: %s - %s\n", m->file, m->note); }
  }
  return nApplied;
}
