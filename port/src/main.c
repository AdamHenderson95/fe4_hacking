// Fire Emblem: Genealogy of the Holy War - PC port frontend.
// Loads the player's own ROM, translates its 65816 code to C, compiles that in memory and runs it
// on a software SNES (LakeSnes PPU/DSP/DMA). Contains no game data.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <sys/stat.h>
#include <SDL.h>
#ifdef _WIN32
#include <windows.h>
#include <commdlg.h>
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#else
#include <dirent.h>
#include <unistd.h>
#define MKDIR(p) mkdir(p, 0755)
#endif

#include "snes.h"
#include "apu.h"
#include "dsp.h"
#include "cart.h"
#include "ppu.h"
#include "rc_rt.h"
#include "rc_jit.h"
#include "recomp.h"
#include "sha1.h"
#include "fe4wide.h"
#include "fe4hover_data.h"
#include "menu.h"
#include "padmap.h"
#include "mods.h"
#include "cheats.h"
#include <utime.h>
#include "kit.h"
#include "music.h"
#include "fe4music_patch.h"

#define PORT_VERSION "0.12"
#define GAME_TITLE "Fire Emblem: Genealogy of the Holy War"
#define NAGA_SHA1 "2b6eb74646a527ba293b0e004db3e0134a28dc6c"

// ---------------- config ----------------
static const char* BTN_NAMES[12] = { "B", "Y", "Select", "Start", "Up", "Down", "Left", "Right", "A", "X", "L", "R" };
static const char* BTN_DEFKEYS[12] = { "Z", "A", "Right Shift", "Return", "Up", "Down", "Left", "Right", "X", "S", "Q", "W" };

typedef struct {
  char rom[1024];
  int scale, fullscreen, aspect43, recompiled, volume, learn, vsync, linear, turbo, widescreen, hoverstats, mute, pauseInMenu, showFps;
  int customMusic, musicVolume;   // music folder tracks on/off, their volume 0-100
  int ffText, ffBattle, ffEnemy, ffCursor;  // automatic speed-ups (1 = off)
  SDL_Keycode keys[12];
  int pad[PAD_BINDINGS];          // gamepad bindings (padmap.h)
} Config;

static Config cfg;
static char baseDir[1024], cfgPath[1100], saveDir[1100], cacheDir[1100];

static void trim(char* s) {
  int n = strlen(s); while(n && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ')) s[--n] = 0;
}

static void config_defaults(void) {
  memset(&cfg, 0, sizeof cfg);
  cfg.scale = 3; cfg.turbo = 4; cfg.ffText = cfg.ffBattle = cfg.ffEnemy = cfg.ffCursor = 1; cfg.widescreen = 1; cfg.hoverstats = 1; cfg.pauseInMenu = 1; cfg.recompiled = 1; cfg.volume = 100; cfg.customMusic = 1; cfg.musicVolume = 100; cfg.learn = 1; cfg.vsync = 1;
  for(int i = 0; i < 12; i++) cfg.keys[i] = SDL_GetKeyFromName(BTN_DEFKEYS[i]);
  memcpy(cfg.pad, PAD_DEFAULTS, sizeof cfg.pad);
}

static void config_save(void) {
  FILE* f = fopen(cfgPath, "w"); if(!f) return;
  fprintf(f, "# FE4 PC port settings\n");
  fprintf(f, "rom=%s\n", cfg.rom);
  fprintf(f, "# window scale (1-8), fullscreen (0/1), aspect: 8:7 (square pixels) or 4:3\n");
  fprintf(f, "scale=%d\nfullscreen=%d\naspect=%s\n", cfg.scale, cfg.fullscreen, cfg.aspect43 ? "4:3" : "8:7");
  fprintf(f, "# smooth scaling (0/1), vsync (0/1)\nsmooth=%d\nvsync=%d\n", cfg.linear, cfg.vsync);
  fprintf(f, "# widescreen=1 shows more of the map and battle backgrounds (16:9); F4 or the F1 menu switches while playing\nwidescreen=%d\n", cfg.widescreen);
  fprintf(f, "# hover_stats=1 adds MT/HIT/AS/AVO to the unit box on the map (also in the F1 menu)\nhover_stats=%d\n", cfg.hoverstats);
  fprintf(f, "# volume 0-100\nvolume=%d\nmute=%d\n", cfg.volume, cfg.mute);
  fprintf(f, "# custom music from the music folder (1 = on) and its volume 0-100\ncustom_music=%d\nmusic_volume=%d\n", cfg.customMusic, cfg.musicVolume);
  fprintf(f, "# in-game menu (F1): pause the game while it is open; FPS counter\npause_in_menu=%d\nshow_fps=%d\n", cfg.pauseInMenu, cfg.showFps);
  fprintf(f, "# fast-forward speed (2-8). Hold Tab (or the right trigger), or press F3 to toggle. Music stays at normal speed.\nfast_forward=%d\n", cfg.turbo);
  fprintf(f, "# automatic speed-ups (1 = off, 2-8 = speed): while text is being written, in battle scenes,\n# during other armies' phases, while moving the cursor on the map. Music stays at normal speed.\nfaster_text=%d\nfaster_battles=%d\nfaster_enemy_phase=%d\nfaster_cursor=%d\n", cfg.ffText, cfg.ffBattle, cfg.ffEnemy, cfg.ffCursor);
  fprintf(f, "# recompiled=1 runs the translated C code; 0 runs the game in the interpreter\nrecompiled=%d\n", cfg.recompiled);
  fprintf(f, "# learn=1 remembers code paths that weren't translated yet, so the next launch translates them too\nlearn=%d\n", cfg.learn);
  fprintf(f, "# keyboard (SDL key names)\n");
  for(int i = 0; i < 12; i++) fprintf(f, "key_%s=%s\n", BTN_NAMES[i], SDL_GetKeyName(cfg.keys[i]));
  fprintf(f, "# gamepad (SDL names: a b x y back start leftshoulder rightshoulder lefttrigger righttrigger leftstick ...;\n# a = bottom button, b = right, x = left, y = top). The d-pad and left stick always move.\n");
  for(int i = 0; i < 12; i++) if(i < 4 || i > 7) fprintf(f, "pad_%s=%s\n", BTN_NAMES[i], pad_input_id(cfg.pad[i]));
  fprintf(f, "pad_FastForward=%s\n", pad_input_id(cfg.pad[PAD_FF]));
  fclose(f);
}

static void config_load(void) {
  config_defaults();
  FILE* f = fopen(cfgPath, "r");
  if(!f) { config_save(); return; }
  char line[1200];
  while(fgets(line, sizeof line, f)) {
    trim(line);
    if(line[0] == '#' || !strchr(line, '=')) continue;
    char* v = strchr(line, '='); *v++ = 0;
    if(!strcmp(line, "rom")) snprintf(cfg.rom, sizeof cfg.rom, "%s", v);
    else if(!strcmp(line, "scale")) cfg.scale = atoi(v);
    else if(!strcmp(line, "fullscreen")) cfg.fullscreen = atoi(v);
    else if(!strcmp(line, "aspect")) cfg.aspect43 = !strcmp(v, "4:3");
    else if(!strcmp(line, "smooth")) cfg.linear = atoi(v);
    else if(!strcmp(line, "vsync")) cfg.vsync = atoi(v);
    else if(!strcmp(line, "widescreen")) cfg.widescreen = atoi(v);
    else if(!strcmp(line, "hover_stats")) cfg.hoverstats = atoi(v);
    else if(!strcmp(line, "mute")) cfg.mute = atoi(v);
    else if(!strcmp(line, "pause_in_menu")) cfg.pauseInMenu = atoi(v);
    else if(!strcmp(line, "show_fps")) cfg.showFps = atoi(v);
    else if(!strcmp(line, "volume")) cfg.volume = atoi(v);
    else if(!strcmp(line, "custom_music")) cfg.customMusic = atoi(v);
    else if(!strcmp(line, "music_volume")) cfg.musicVolume = atoi(v);
    else if(!strcmp(line, "fast_forward")) cfg.turbo = atoi(v);
    else if(!strcmp(line, "faster_text")) cfg.ffText = atoi(v);
    else if(!strcmp(line, "faster_battles")) cfg.ffBattle = atoi(v);
    else if(!strcmp(line, "faster_enemy_phase")) cfg.ffEnemy = atoi(v);
    else if(!strcmp(line, "faster_cursor")) cfg.ffCursor = atoi(v);
    else if(!strcmp(line, "recompiled")) cfg.recompiled = atoi(v);
    else if(!strcmp(line, "learn")) cfg.learn = atoi(v);
    else if(!strncmp(line, "pad_", 4)) {
      int p = pad_input_from_id(v);
      if(p != -2) { if(!strcmp(line + 4, "FastForward")) cfg.pad[PAD_FF] = p; else for(int i = 0; i < 12; i++) if(!strcmp(line + 4, BTN_NAMES[i])) cfg.pad[i] = p; }
    }
    else if(!strncmp(line, "key_", 4)) {
      for(int i = 0; i < 12; i++) if(!strcmp(line + 4, BTN_NAMES[i])) {
        SDL_Keycode k = SDL_GetKeyFromName(v); if(k != SDLK_UNKNOWN) cfg.keys[i] = k;
      }
    }
  }
  fclose(f);
  if(cfg.scale < 1) cfg.scale = 1; if(cfg.scale > 8) cfg.scale = 8;
  if(cfg.turbo < 2) cfg.turbo = 2; if(cfg.turbo > 8) cfg.turbo = 8;
  int* ff[4] = { &cfg.ffText, &cfg.ffBattle, &cfg.ffEnemy, &cfg.ffCursor };
  for(int i = 0; i < 4; i++) { if(*ff[i] < 1) *ff[i] = 1; if(*ff[i] > 8) *ff[i] = 8; }
  if(cfg.volume < 0) cfg.volume = 0; if(cfg.volume > 100) cfg.volume = 100;
}

// ---------------- files ----------------
static uint8_t* read_file(const char* path, int* len) {
  FILE* f = fopen(path, "rb"); if(!f) return NULL;
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t* d = malloc(n + 1);
  if(fread(d, 1, n, f) != (size_t)n) { fclose(f); free(d); return NULL; }
  fclose(f); d[n] = 0; *len = (int)n; return d;
}
static int write_file(const char* path, const void* d, int n) {
  FILE* f = fopen(path, "wb"); if(!f) return 0;
  int ok = fwrite(d, 1, n, f) == (size_t)n; fclose(f); return ok;
}
static int file_exists(const char* p) { struct stat st; return stat(p, &st) == 0; }

static void msg(const char* title, const char* text, int error) {
  fprintf(error ? stderr : stdout, "%s: %s\n", title, text);
  SDL_ShowSimpleMessageBox(error ? SDL_MESSAGEBOX_ERROR : SDL_MESSAGEBOX_INFORMATION, title, text, NULL);
}

// ---------------- ROM ----------------
static uint8_t* romData; static int romLen; static char romSha[41]; static char romBase[256];
static uint8_t romHdr[512]; static int romHadHdr;   // the copier header the ROM file had (mods made for it)
static char gameSha[41];                            // the ROM as played: after mods (names the translation)

// strip a copier header; check it's FE4 (ExHiROM header at $40FFC0 says FIREEMBLEM4)
static int rom_check(uint8_t* d, int* len) {
  romHadHdr = 0;
  if((*len & 0x7fff) == 0x200) { memcpy(romHdr, d, 0x200); romHadHdr = 1; memmove(d, d + 0x200, *len - 0x200); *len -= 0x200; }
  if(*len < 0x410000) return 0;
  return !memcmp(d + 0x40ffc0, "FIREEMBLEM4", 11);
}

static int try_rom(const char* path) {
  int n; uint8_t* d = read_file(path, &n);
  if(!d) return 0;
  if(!rom_check(d, &n)) { free(d); return 0; }
  romData = d; romLen = n;
  sha1(d, n, romSha);
  const char* s = strrchr(path, '/'); const char* s2 = strrchr(path, '\\'); if(s2 > s) s = s2;
  snprintf(romBase, sizeof romBase, "%s", s ? s + 1 : path);
  char* dot = strrchr(romBase, '.'); if(dot) *dot = 0;
  return 1;
}

static int scan_dir_for_rom(const char* dir, char* out, int outn) {
#ifdef _WIN32
  char pat[1200]; snprintf(pat, sizeof pat, "%s*.*", dir);
  WIN32_FIND_DATAA fd; HANDLE h = FindFirstFileA(pat, &fd);
  if(h == INVALID_HANDLE_VALUE) return 0;
  int found = 0;
  do {
    const char* ext = strrchr(fd.cFileName, '.');
    if(ext && (!_stricmp(ext, ".sfc") || !_stricmp(ext, ".smc"))) {
      snprintf(out, outn, "%s%s", dir, fd.cFileName);
      if(try_rom(out)) { found = 1; break; }
    }
  } while(FindNextFileA(h, &fd));
  FindClose(h);
  return found;
#else
  DIR* d = opendir(dir); if(!d) return 0;
  struct dirent* e; int found = 0;
  while((e = readdir(d))) {
    const char* ext = strrchr(e->d_name, '.');
    if(ext && (!strcasecmp(ext, ".sfc") || !strcasecmp(ext, ".smc"))) {
      snprintf(out, outn, "%s%s", dir, e->d_name);
      if(try_rom(out)) { found = 1; break; }
    }
  }
  closedir(d);
  return found;
#endif
}

static int pick_rom_dialog(char* out, int outn) {
#ifdef _WIN32
  OPENFILENAMEA ofn; memset(&ofn, 0, sizeof ofn);
  out[0] = 0;
  ofn.lStructSize = sizeof ofn;
  ofn.lpstrFilter = "SNES ROM (*.sfc;*.smc)\0*.sfc;*.smc\0All files\0*.*\0";
  ofn.lpstrFile = out; ofn.nMaxFile = outn;
  ofn.lpstrTitle = "Select your Fire Emblem: Genealogy of the Holy War ROM";
  ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
  return GetOpenFileNameA(&ofn);
#else
  (void)out; (void)outn; return 0;
#endif
}

// ---------------- recompilation ----------------
static void* jitHandle;
static int widePatched, hoverPatched, musicPatched;
// write the on/off flags of the switchable game changes into the ROM image (and the running copy)
static void set_rom_flags(Snes* snes) {
  for(int k = 0; k < 2; k++) {
    uint8_t* r = k ? (snes ? snes->cart->rom : NULL) : romData;
    if(!r) continue;
    if(widePatched) fe4wide_setRomFlag(r, romLen, cfg.widescreen);
    if(hoverPatched) { r[FE4_HOVER_FLAG] = cfg.hoverstats ? 1 : 0; r[FE4_HOVER_FLAG + 1] = 0; }
  }
}

typedef struct { RcGenEntry* e; int n, cap; } EntList;
static void ents_load(EntList* L, const char* path, int mincount) {
  FILE* f = fopen(path, "r"); if(!f) return;
  char line[128];
  while(fgets(line, sizeof line, f)) {
    unsigned pc, fs, cnt = 1;
    if(line[0] == '#') continue;
    if(sscanf(line, "%x %u %u", &pc, &fs, &cnt) >= 2 && (int)cnt >= mincount && fs <= 4) {
      if(L->n == L->cap) { L->cap = L->cap ? L->cap * 2 : 4096; L->e = realloc(L->e, L->cap * sizeof *L->e); }
      L->e[L->n].pc = pc; L->e[L->n].fs = fs; L->n++;
    }
  }
  fclose(f);
}

static char titleTag[300]; // e.g. "test play: myhack"
static void set_title(SDL_Window* w, const char* extra) {
  if(!extra && titleTag[0]) extra = titleTag;
  char t[512]; snprintf(t, sizeof t, "%s%s%s", GAME_TITLE, extra ? " - " : "", extra ? extra : "");
  SDL_SetWindowTitle(w, t);
}

// the cache keeps one translation per ROM version (each hack build or randomizer seed makes one):
// keep the most recently used few
static void prune_cache(const char* keep) {
  enum { KEEP = 6 };
  char names[64][300]; long long times[64]; int n = 0;
#ifdef _WIN32
  char pat[1200]; snprintf(pat, sizeof pat, "%sfe4_*.c", cacheDir);
  WIN32_FIND_DATAA fd; HANDLE h = FindFirstFileA(pat, &fd);
  if(h != INVALID_HANDLE_VALUE) { do { if(n < 64) { snprintf(names[n], 300, "%s", fd.cFileName);
    times[n++] = ((long long)fd.ftLastWriteTime.dwHighDateTime << 32) | fd.ftLastWriteTime.dwLowDateTime; } } while(FindNextFileA(h, &fd)); FindClose(h); }
#else
  DIR* d = opendir(cacheDir);
  if(d) { struct dirent* e; while((e = readdir(d))) if(!strncmp(e->d_name, "fe4_", 4) && strstr(e->d_name, ".c") && n < 64) {
    char p[1400]; snprintf(p, sizeof p, "%s%s", cacheDir, e->d_name); struct stat st; if(stat(p, &st)) continue;
    snprintf(names[n], 300, "%s", e->d_name); times[n++] = st.st_mtime; } closedir(d); }
#endif
  while(n > KEEP) {
    int old = -1;
    for(int i = 0; i < n; i++) if(strcmp(names[i], keep) && (old < 0 || times[i] < times[old])) old = i;
    if(old < 0) break;
    char p[1400]; snprintf(p, sizeof p, "%s%s", cacheDir, names[old]); remove(p);
    names[old][0] = 0; memmove(names + old, names + old + 1, (n - old - 1) * 300); memmove(times + old, times + old + 1, (n - old - 1) * sizeof *times); n--;
  }
}

static int recompile(SDL_Window* win, Snes* snes) {
  (void)snes;
  EntList L = { 0 };
  char p[1200];
  snprintf(p, sizeof p, "%sfe4port.cov", baseDir); ents_load(&L, p, 1);
  snprintf(p, sizeof p, "%slearned.cov", cacheDir); ents_load(&L, p, 1);
  // cache key: ROM hash + entry list
  char keySrc[64]; uint32_t eh = 2166136261u;
  for(int i = 0; i < L.n; i++) { eh = (eh ^ L.e[i].pc) * 16777619u; eh = (eh ^ L.e[i].fs) * 16777619u; }
  snprintf(keySrc, sizeof keySrc, "%.12s_%08x%s%s%s", gameSha, eh, widePatched ? "_w2" : "", hoverPatched ? "_h2" : "", musicPatched ? "_m1" : "");
  char srcPath[1200]; snprintf(srcPath, sizeof srcPath, "%sfe4_%s.c", cacheDir, keySrc);
  if(!file_exists(srcPath)) {
    set_title(win, "translating the game's code to C (first launch)...");
    SDL_PumpEvents();
    FILE* f = fopen(srcPath, "w");
    if(!f) { fprintf(stderr, "can't write %s\n", srcPath); free(L.e); return 0; }
    uint32_t t0 = SDL_GetTicks();
    RcGenStats st = rc_generate(romData, romLen, L.e, L.n, 1, f);
    fclose(f);
    printf("translated %d blocks (%d instructions) in %u ms -> %s\n", st.blocks, st.instrs, SDL_GetTicks() - t0, srcPath);
  } else utime(srcPath, NULL); // mark as recently used
  { char k[300]; snprintf(k, sizeof k, "fe4_%s.c", keySrc); prune_cache(k); }
  free(L.e);
  set_title(win, "compiling...");
  SDL_PumpEvents();
  int n; char* src = (char*)read_file(srcPath, &n);
  if(!src) return 0;
  const RcEntry* tab; int cnt;
  uint32_t t0 = SDL_GetTicks();
  int ok = rc_jitCompile(src, &tab, &cnt, &jitHandle);
  free(src);
  if(!ok) {
    fprintf(stderr, "compile failed:\n%s\n", rc_jitError());
    remove(srcPath);
    return 0;
  }
  rc_setBlocks(tab, cnt);
  printf("compiled %d blocks in %u ms\n", cnt, SDL_GetTicks() - t0);
  return 1;
}

// merge newly seen block entries into cache/learned.cov
static void save_learned(void) {
  char tmp[1200], dst[1200];
  snprintf(tmp, sizeof tmp, "%slearned.new", cacheDir);
  snprintf(dst, sizeof dst, "%slearned.cov", cacheDir);
  if(rc_saveCoverage(tmp, 0) <= 0) { remove(tmp); return; }
  EntList a = { 0 }, b = { 0 };
  ents_load(&a, dst, 1);
  ents_load(&b, tmp, 2); // something reached at least twice
  remove(tmp);
  if(!b.n) { free(a.e); return; }
  FILE* f = fopen(dst, "w");
  if(f) {
    for(int i = 0; i < a.n; i++) fprintf(f, "%06X %u\n", a.e[i].pc, a.e[i].fs);
    int added = 0;
    for(int i = 0; i < b.n; i++) {
      int dup = 0;
      for(int j = 0; j < a.n && !dup; j++) dup = a.e[j].pc == b.e[i].pc && a.e[j].fs == b.e[i].fs;
      if(!dup) { fprintf(f, "%06X %u\n", b.e[i].pc, b.e[i].fs); added++; }
    }
    fclose(f);
    printf("learned %d new code entry points\n", added);
  }
  free(a.e); free(b.e);
}

// ---------------- save data ----------------
static uint8_t lastSram[0x20000];
static void sram_path(char* p, int n) { snprintf(p, n, "%s%s.srm", saveDir, romBase); }
static void sram_load(Snes* snes) {
  char p[1200]; sram_path(p, sizeof p);
  int n; uint8_t* d = read_file(p, &n);
  if(d) { snes_loadBattery(snes, d, n); free(d); }
  if(snes->cart->ram) memcpy(lastSram, snes->cart->ram, snes->cart->ramSize);
}
static void sram_flush(Snes* snes) {
  if(!snes->cart->ram || !memcmp(lastSram, snes->cart->ram, snes->cart->ramSize)) return;
  char p[1200]; sram_path(p, sizeof p);
  if(write_file(p, snes->cart->ram, snes->cart->ramSize)) memcpy(lastSram, snes->cart->ram, snes->cart->ramSize);
}
static int state_io(Snes* snes, int slot, int save) {
  char p[1200]; snprintf(p, sizeof p, "%s%s.state%d", saveDir, romBase, slot);
  if(save) {
    int n = snes_saveState(snes, NULL); uint8_t* d = malloc(n);
    snes_saveState(snes, d); int ok = write_file(p, d, n); free(d);
    if(ok && musicPatched) { uint8_t m[256]; music_state_save(m); char q[1220]; snprintf(q, sizeof q, "%s.music", p); write_file(q, m, music_state_size()); }
    return ok;
  }
  int n; uint8_t* d = read_file(p, &n); if(!d) return 0;
  int ok = snes_loadState(snes, d, n); free(d);
  if(ok && musicPatched) {
    char q[1220]; snprintf(q, sizeof q, "%s.music", p); int mn; uint8_t* m = read_file(q, &mn);
    music_state_load(m, m ? mn : 0); free(m);
  }
  return ok;
}

static void state_info(int slot, int* used, char* when, int n) {
  char p[1200]; snprintf(p, sizeof p, "%s%s.state%d", saveDir, romBase, slot);
  struct stat st;
  *used = stat(p, &st) == 0;
  when[0] = 0;
  if(*used) { struct tm* t = localtime(&st.st_mtime); if(t) strftime(when, n, "%b %d %H:%M", t); }
}

// ---------------- input ----------------
static SDL_GameController* pads[4];
static uint16_t keyState, padState;
static int padTurbo;

static void pad_open_all(void) {
  for(int i = 0; i < SDL_NumJoysticks() && i < 4; i++)
    if(SDL_IsGameController(i) && !pads[i]) pads[i] = SDL_GameControllerOpen(i);
}

// test hook: FE4_VPAD=script makes a virtual gamepad and plays "iteration button value" lines on it
// (button: an SDL name like a/b/x/y/start, or lt/rt for the triggers; value 1/0)
static SDL_Joystick* vpad; static FILE* vpadScript; static long vpadIter;
static void vpad_init(void) {
  const char* p = getenv("FE4_VPAD"); if(!p) return;
  SDL_VirtualJoystickDesc d; memset(&d, 0, sizeof d);
  d.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION; d.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
  d.naxes = SDL_CONTROLLER_AXIS_MAX; d.nbuttons = SDL_CONTROLLER_BUTTON_MAX; d.name = "Virtual test pad";
  for(int i = 0; i < SDL_CONTROLLER_BUTTON_MAX; i++) d.button_mask |= 1u << i;
  for(int i = 0; i < SDL_CONTROLLER_AXIS_MAX; i++) d.axis_mask |= 1u << i;
  int idx = SDL_JoystickAttachVirtualEx(&d);
  if(idx >= 0) vpad = SDL_JoystickOpen(idx);
  vpadScript = fopen(p, "r");
  printf("virtual pad: %s\n", vpad ? "attached" : SDL_GetError());
}
static void vpad_step(void) {
  if(!vpad || !vpadScript) return;
  vpadIter++;
  static long nextIter = -1; static char btn[32]; static int val;
  for(;;) {
    if(nextIter < 0) { if(fscanf(vpadScript, "%ld %31s %d", &nextIter, btn, &val) != 3) { fclose(vpadScript); vpadScript = NULL; return; } }
    if(nextIter > vpadIter) return;
    if(!strcmp(btn, "wait")) { // "0 wait 0": hold the script until a file named vpad.go appears
      FILE* g = fopen("vpad.go", "r"); if(!g) return; fclose(g); remove("vpad.go"); nextIter = -1; vpadIter = 0; continue;
    }
    if(!strcmp(btn, "lt") || !strcmp(btn, "rt")) SDL_JoystickSetVirtualAxis(vpad, !strcmp(btn, "lt") ? SDL_CONTROLLER_AXIS_TRIGGERLEFT : SDL_CONTROLLER_AXIS_TRIGGERRIGHT, val ? 32767 : 0);
    else SDL_JoystickSetVirtualButton(vpad, SDL_GameControllerGetButtonFromString(btn), val);
    printf("vpad iter %ld: %s=%d\n", vpadIter, btn, val);
    nextIter = -1;
  }
}

static uint16_t pad_poll(void) {
  uint16_t m = 0;
  padTurbo = 0;
  for(int i = 0; i < 4; i++) if(pads[i]) {
    SDL_GameController* g = pads[i];
    // bindings from the settings (default: Nintendo layout by position: bottom = B, right = A, left = Y, top = X)
    for(int b = 0; b < 12; b++) if(pad_input_down(g, cfg.pad[b])) m |= 1 << b;
    if(SDL_GameControllerGetButton(g, SDL_CONTROLLER_BUTTON_DPAD_UP)) m |= 1 << 4;
    if(SDL_GameControllerGetButton(g, SDL_CONTROLLER_BUTTON_DPAD_DOWN)) m |= 1 << 5;
    if(SDL_GameControllerGetButton(g, SDL_CONTROLLER_BUTTON_DPAD_LEFT)) m |= 1 << 6;
    if(SDL_GameControllerGetButton(g, SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) m |= 1 << 7;
    int ax = SDL_GameControllerGetAxis(g, SDL_CONTROLLER_AXIS_LEFTX), ay = SDL_GameControllerGetAxis(g, SDL_CONTROLLER_AXIS_LEFTY);
    if(ay < -16000) m |= 1 << 4; if(ay > 16000) m |= 1 << 5;
    if(ax < -16000) m |= 1 << 6; if(ax > 16000) m |= 1 << 7;
    if(pad_input_down(g, cfg.pad[PAD_FF])) padTurbo = 1;
  }
  return m;
}

// ---------------- test movie (for automated checks) ----------------
#include "../tools/movie.h"

// ---------------- battle previews (the kit's "Watch in battle") ----------------
// --freeze ADDR VAL FROM: from frame FROM on, every write to ADDR (bank $7E/$7F or a mirror) stores VAL
static uint32_t frzAdr[16]; static uint8_t frzVal[16]; static int frzFrom[16], nFrz, frzFrame;
static uint8_t freeze_map(Snes* s, uint32_t adr, uint8_t val) {
  (void)s;
  uint8_t bank = adr >> 16; uint32_t a = adr & 0xffff, w;
  if(bank == 0x7e || bank == 0x7f) w = ((bank & 1) << 16) | a;
  else if((bank & 0x7f) < 0x40 && a < 0x2000) w = a; else return val;
  for(int i = 0; i < nFrz; i++) if(frzAdr[i] == w && frzFrame >= frzFrom[i]) return frzVal[i];
  return val;
}

// ---------------- main ----------------
static void usage(void) {
  printf("FE4 PC port %s\n"
    "usage: fe4 [rom.sfc] [--play rom.sfc] [--no-mods] [--interp] [--frames N --movie file --shot out.bmp] [--fast]\n"
    "  --play rom.sfc  test play: run this ROM without mods and without making it the default ROM\n"
    "  --turbo-until N        run as fast as possible (no sound) until frame N\n"
    "  --loop-at N            after --turbo-until, go back to that frame when frame N is reached\n"
    "  --freeze ADDR VAL FROM from frame FROM, writes to RAM ADDR (hex) store VAL (hex)\n"
    "  --title TEXT           text for the window title\n"
    "  --music DIR            custom music from DIR instead of the music folder\n"
    "  --make-pcm IN OUT      write an MSU-1 track (.pcm) for emulators from a music file, then quit\n"
    "  --state-cache FILE     with --turbo-until: start from FILE if it holds that frame, else save it there\n", PORT_VERSION);
}

int main(int argc, char** argv) {
  // FE4.exe --make-pcm IN OUT: an MSU-1 track for emulators from any music file the port plays (used by the kit)
  if(argc >= 4 && !strcmp(argv[1], "--make-pcm")) {
    char err[600] = "";
    int ok = music_convert(argv[2], argv[3], err, sizeof err);
    if(!ok) fprintf(stderr, "%s\n", err);
    return ok ? 0 : 1;
  }
  const char* romArg = NULL; int forceInterp = 0, maxFrames = 0, fast = 0, forceSpeed = 0;
  const char* movieArg = NULL; const char* shotArg = NULL; const char* wavArg = NULL; const char* musicArg = NULL;
  int turboUntil = 0, loopAt = 0; const char* titleArg = NULL; const char* stateCache = NULL;
  const char* shotDir = NULL; int shotEvery = 0; const char* stateArg = NULL;
  int noMods = 0, testPlay = 0;
  for(int i = 1; i < argc; i++) {
    if(!strcmp(argv[i], "--interp")) forceInterp = 1;
    else if(!strcmp(argv[i], "--no-mods")) noMods = 1;
    else if(!strcmp(argv[i], "--play") && i + 1 < argc) { romArg = argv[++i]; testPlay = 1; noMods = 1; }
    else if(!strcmp(argv[i], "--frames") && i + 1 < argc) maxFrames = atoi(argv[++i]);
    else if(!strcmp(argv[i], "--movie") && i + 1 < argc) movieArg = argv[++i];
    else if(!strcmp(argv[i], "--shot") && i + 1 < argc) shotArg = argv[++i];
    else if(!strcmp(argv[i], "--fast")) fast = 1;
    else if(!strcmp(argv[i], "--speed") && i + 1 < argc) forceSpeed = atoi(argv[++i]);
    else if(!strcmp(argv[i], "--state") && i + 1 < argc) stateArg = argv[++i];
    else if(!strcmp(argv[i], "--shotdir") && i + 2 < argc) { shotDir = argv[++i]; shotEvery = atoi(argv[++i]); }
    else if(!strcmp(argv[i], "--wav") && i + 1 < argc) wavArg = argv[++i];
    else if(!strcmp(argv[i], "--music") && i + 1 < argc) musicArg = argv[++i];
    else if(!strcmp(argv[i], "--turbo-until") && i + 1 < argc) turboUntil = atoi(argv[++i]);
    else if(!strcmp(argv[i], "--loop-at") && i + 1 < argc) loopAt = atoi(argv[++i]);
    else if(!strcmp(argv[i], "--title") && i + 1 < argc) titleArg = argv[++i];
    else if(!strcmp(argv[i], "--state-cache") && i + 1 < argc) stateCache = argv[++i];
    else if(!strcmp(argv[i], "--freeze") && i + 3 < argc && nFrz < 16) {
      frzAdr[nFrz] = strtol(argv[i + 1], NULL, 16); frzVal[nFrz] = strtol(argv[i + 2], NULL, 16); frzFrom[nFrz++] = atoi(argv[i + 3]); i += 3;
      snes_writeMap = freeze_map; }
    else if(!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) { usage(); return 0; }
    else if(argv[i][0] != '-') romArg = argv[i];
  }
  // positional face buttons on every pad (Switch pads would otherwise swap A/B and X/Y)
  SDL_SetHint(SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS, "0");
  if(SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER | SDL_INIT_EVENTS) != 0) {
    fprintf(stderr, "SDL_Init: %s\n", SDL_GetError()); return 1;
  }
  char* bp = SDL_GetBasePath();
  snprintf(baseDir, sizeof baseDir, "%s", bp ? bp : "./"); SDL_free(bp);
  snprintf(cfgPath, sizeof cfgPath, "%sfe4port.ini", baseDir);
#ifdef _WIN32
  { // windowed build has no console: keep a log next to the program
    char lp[1100]; snprintf(lp, sizeof lp, "%sfe4port.log", baseDir);
    freopen(lp, "w", stdout); freopen(lp, "a", stderr);
    setvbuf(stdout, NULL, _IONBF, 0);
  }
#endif
  snprintf(saveDir, sizeof saveDir, "%ssaves/", baseDir); MKDIR(saveDir);
  snprintf(cacheDir, sizeof cacheDir, "%scache/", baseDir); MKDIR(cacheDir);
  config_load();

  // ---- find the ROM ----
  char romPath[1100] = "";
  int haveRom = 0;
  if(romArg) { snprintf(romPath, sizeof romPath, "%s", romArg); haveRom = try_rom(romPath); }
  if(testPlay && !haveRom) { msg(GAME_TITLE, "Test play: that file isn't a Fire Emblem: Genealogy of the Holy War ROM.", 1); return 1; }
  if(!haveRom && cfg.rom[0]) { snprintf(romPath, sizeof romPath, "%s", cfg.rom); haveRom = try_rom(romPath); }
  if(!haveRom) haveRom = scan_dir_for_rom(baseDir, romPath, sizeof romPath);
  if(!haveRom) {
#ifdef _WIN32
    msg(GAME_TITLE, "This port runs from your own copy of the game.\n\nPick your Fire Emblem: Genealogy of the Holy War ROM "
      "(the Project Naga English patch is recommended). You only need to do this once.", 0);
    while(!haveRom && pick_rom_dialog(romPath, sizeof romPath)) {
      haveRom = try_rom(romPath);
      if(!haveRom) msg(GAME_TITLE, "That file isn't a Fire Emblem: Genealogy of the Holy War ROM. Please pick another.", 1);
    }
#endif
    if(!haveRom) { msg(GAME_TITLE, "No Fire Emblem: Genealogy of the Holy War ROM found. Put your .sfc/.smc file next to the program "
      "or pass it on the command line.", 1); return 1; }
  }
  if(testPlay) snprintf(titleTag, sizeof titleTag, "test play: %s", romBase);
  if(titleArg) snprintf(titleTag, sizeof titleTag, "%s", titleArg);
  if(!testPlay && strcmp(cfg.rom, romPath)) { snprintf(cfg.rom, sizeof cfg.rom, "%s", romPath); config_save(); }
  printf("ROM: %s (sha1 %s)%s%s\n", romPath, romSha, strcmp(romSha, NAGA_SHA1) ? " [not the Project Naga 1.0 image - running it anyway]" : " [Project Naga 1.0]",
    testPlay ? " (test play)" : "");

  // ---- mods: .ips / .bps patches from the mods folder, in load order ----
  { char md[1100]; snprintf(md, sizeof md, "%smods/", baseDir); mods_init(md); }
  int modsApplied = noMods ? 0 : mods_apply(&romData, &romLen, romHdr, romHadHdr);
  if(modsApplied) {
    sha1(romData, romLen, gameSha);
    char t[256]; snprintf(t, sizeof t, "%s+mods-%08x", romBase, (unsigned)mods_set_hash()); snprintf(romBase, sizeof romBase, "%s", t);
    printf("%d mod(s) applied; saves: %s\n", modsApplied, romBase);
  } else memcpy(gameSha, romSha, sizeof gameSha);
  kit_init(baseDir, cacheDir);

  // ---- game changes that can be switched on and off while playing (a flag word in ROM each) ----
  // widescreen: units are drawn in the extra area too
  widePatched = fe4wide_patchRom(romData, romLen);
  printf("widescreen units: %s\n", widePatched ? "available" : "ROM not recognised, map units limited to the 4:3 area");
  // map hover box: MT/HIT/AS/AVO
  hoverPatched = fe4patch_apply(romData, romLen, FE4_HOVER);
  printf("hover stats: %s\n", hoverPatched ? "available" : "ROM not recognised, not available");
  // custom music: an MSU-1 chip that plays files from the music folder
  musicPatched = fe4patch_apply(romData, romLen, FE4_MUSIC);
  { char md[1100];
    if(musicArg) { size_t l = strlen(musicArg); snprintf(md, sizeof md, "%s%s", musicArg, l && musicArg[l - 1] != '/' && musicArg[l - 1] != '\\' ? "/" : ""); }
    else { snprintf(md, sizeof md, "%smusic/", baseDir); MKDIR(md); }
    music_init(md); }
  music_set_enabled(cfg.customMusic);
  printf("custom music: %s, %d track(s) in the music folder\n", musicPatched ? "available" : "ROM not recognised, not available", music_count());
  if(musicPatched) { snes_msuRead = music_read; snes_msuWrite = music_write; }
  set_rom_flags(NULL);

  // ---- machine ----
  Snes* snes = snes_init();
  if(!snes_loadRom(snes, romData, romLen)) { msg(GAME_TITLE, "Couldn't load the ROM.", 1); return 1; }
  sram_load(snes);

  // ---- window ----
  static uint32_t wideBuf[FE4WIDE_W * 239];
  int wideOn = cfg.widescreen;
  if(wideOn) fe4wide_attach(snes, wideBuf);
  #define VIEW_W (wideOn ? FE4WIDE_W : 256)
  #define LOGICAL_W ((cfg.aspect43 ? VIEW_W * 16 / 7 : VIEW_W * 2))  // picture width for a 448-line height
  int ww = (cfg.aspect43 ? VIEW_W * 8 / 7 : VIEW_W) * cfg.scale, wh = 224 * cfg.scale;
  SDL_Window* win = SDL_CreateWindow(GAME_TITLE, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, ww, wh,
    SDL_WINDOW_RESIZABLE | (cfg.fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) | (shotArg && fast ? SDL_WINDOW_HIDDEN : 0));
  if(!win) { fprintf(stderr, "window: %s\n", SDL_GetError()); return 1; }
  SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, cfg.linear ? "linear" : "nearest");
  SDL_Renderer* ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | (cfg.vsync && !fast ? SDL_RENDERER_PRESENTVSYNC : 0));
  if(!ren) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
  { SDL_RendererInfo ri; if(ren && !SDL_GetRendererInfo(ren, &ri)) printf("renderer: %s\n", ri.name); }
  SDL_Texture* tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, 512, 448);
  SDL_Texture* wtex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, FE4WIDE_W, 224);
  SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_NONE); SDL_SetTextureBlendMode(wtex, SDL_BLENDMODE_NONE);
  SDL_SetTextureScaleMode(tex, cfg.linear ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
  SDL_SetTextureScaleMode(wtex, cfg.linear ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
  menu_init(win, ren);
  SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren); SDL_RenderPresent(ren);

  // ---- translate + compile ----
  int recompiled = 0;
  if(cfg.recompiled && !forceInterp) {
    recompiled = recompile(win, snes);
    if(!recompiled) printf("running in the interpreter instead\n");
  }
  rc_recordMisses = recompiled && cfg.learn;
  set_title(win, NULL);

  // ---- audio ----
  SDL_AudioSpec want = { 0 }, have;
  want.freq = 48000; want.format = AUDIO_S16; want.channels = 2; want.samples = 1024;
  SDL_AudioDeviceID dev = fast ? 0 : SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
  int16_t* abuf = malloc(8192 * 4);
  double audioCarry = 0;
  if(dev) SDL_PauseAudioDevice(dev, 0);

  if(movieArg) movie_load(movieArg);
  int frame0 = 0;
  if(stateArg) { // test states from tools/lockstep: 4-byte frame number + LakeSnes state
    int n; uint8_t* d = read_file(stateArg, &n);
    if(d && n > 4 && snes_loadState(snes, d + 4, n - 4)) frame0 = *(int*)d; else fprintf(stderr, "couldn't load %s\n", stateArg);
    free(d);
  }
  FILE* wav = NULL; uint32_t wavBytes = 0;
  if(wavArg && (wav = fopen(wavArg, "wb"))) { uint8_t hdr[44] = { 0 }; fwrite(hdr, 1, 44, wav); }
  vpad_init(); pad_open_all();
  static uint8_t px[512 * 480 * 4];
  int running = 1, paused = 0, turboHeld = 0, turboToggle = 0, speed = 1, slot = 1, frame = frame0;
  uint8_t* loopState = NULL; int loopLen = 0;
  if(turboUntil && stateCache) { // a state saved at turboUntil by an earlier preview (4-byte frame + state)
    int n; uint8_t* d = read_file(stateCache, &n);
    if(d && n > 4 && *(int*)d == turboUntil && snes_loadState(snes, d + 4, n - 4)) frame = turboUntil;
    free(d);
    if(frame >= turboUntil && loopAt) { loopLen = snes_saveState(snes, NULL); loopState = malloc(loopLen); snes_saveState(snes, loopState); }
  }
  // automatic speed-ups: what the game is doing, from its RAM (checked after every emulated frame)
  //   text: the dialogue renderer's text pointer ($186A, 24-bit) moved recently
  //   battle: the game's frame-handler pointer ($00D7) is the battle scene's ($C144)
  //   other armies' phase: the army slot whose turn it is ($0D91) isn't 0 (the player)
  uint32_t lastTextPtr = 0; int textRecent = 0, inBattle = 0, otherPhase = 0;
  int fpsFrames = 0; Uint32 fpsT0 = SDL_GetTicks(); float fps = 0;
  MenuState ms; memset(&ms, 0, sizeof ms);
  ms.widescreen = &cfg.widescreen; ms.aspect43 = &cfg.aspect43; ms.smooth = &cfg.linear; ms.vsync = &cfg.vsync;
  ms.fullscreen = &cfg.fullscreen; ms.scale = &cfg.scale; ms.volume = &cfg.volume; ms.mute = &cfg.mute;
  ms.pad = cfg.pad; ms.padCount = 0;
  ms.ffText = &cfg.ffText; ms.ffBattle = &cfg.ffBattle; ms.ffEnemy = &cfg.ffEnemy; ms.ffCursor = &cfg.ffCursor;
  ms.customMusic = &cfg.customMusic; ms.musicVolume = &cfg.musicVolume; ms.musicAvail = musicPatched; ms.musicDir = music_dir();
  ms.turbo = &cfg.turbo; ms.ffToggle = &turboToggle; ms.hoverstats = &cfg.hoverstats; ms.pauseInMenu = &cfg.pauseInMenu;
  ms.showFps = &cfg.showFps; ms.paused = &paused; ms.slot = &slot; ms.keys = cfg.keys;
  ms.version = PORT_VERSION; ms.romName = romBase; ms.recompiled = recompiled; ms.hoverActive = hoverPatched;
  static char romInfo[160];
  snprintf(romInfo, sizeof romInfo, "SHA-1 %s%s", romSha, strcmp(romSha, NAGA_SHA1) ? " (not the Project Naga 1.0 image)" : " (Project Naga 1.0)");
  ms.romInfo = romInfo;
  ms.testPlay = testPlay; ms.modsApplied = modsApplied;
  int restartAfter = 0;
  char randoName[200] = "";
  if(modsApplied) { char t[64]; snprintf(t, sizeof t, "%d mod%s in use", modsApplied, modsApplied > 1 ? "s" : ""); menu_notify(t); }
  // apply graphics settings (from the menu or a shortcut)
  #define APPLY_VIDEO() do { \
    if(wideOn != cfg.widescreen) { wideOn = cfg.widescreen; if(wideOn) fe4wide_attach(snes, wideBuf); else snes->ppu->wideBuf = NULL; } \
    SDL_SetWindowFullscreen(win, cfg.fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0); \
    if(!cfg.fullscreen) SDL_SetWindowSize(win, (cfg.aspect43 ? VIEW_W * 8 / 7 : VIEW_W) * cfg.scale, 224 * cfg.scale); \
    SDL_SetTextureScaleMode(tex, cfg.linear ? SDL_ScaleModeLinear : SDL_ScaleModeNearest); \
    SDL_SetTextureScaleMode(wtex, cfg.linear ? SDL_ScaleModeLinear : SDL_ScaleModeNearest); \
    SDL_RenderSetVSync(ren, cfg.vsync && !fast); \
    set_rom_flags(snes); \
  } while(0)
  uint64_t freq = SDL_GetPerformanceFrequency(), last = SDL_GetPerformanceCounter();
  double acc = 0;
  const double frameTime = 1.0 / 60.0988;
  while(running) {
    SDL_Event ev;
    while(SDL_PollEvent(&ev)) {
      int wasVisible = menu_visible();
      if(!menu_capturing_key() && ev.type == SDL_KEYDOWN && !ev.key.repeat &&
         (ev.key.keysym.sym == SDLK_F1 || (ev.key.keysym.sym == SDLK_ESCAPE && !menu_popup_open()))) { menu_toggle(); keyState = 0; continue; }
      if(menu_event(&ev, &ms)) { if(ev.type == SDL_KEYUP) { for(int i = 0; i < 12; i++) if(cfg.keys[i] == ev.key.keysym.sym) keyState &= ~(1 << i); } continue; }
      if(ev.type == SDL_CONTROLLERBUTTONDOWN && ev.cbutton.button == SDL_CONTROLLER_BUTTON_RIGHTSTICK) { menu_toggle(); keyState = 0; continue; }
      if(wasVisible && (ev.type == SDL_KEYDOWN) && !(ev.key.keysym.sym >= SDLK_F1 && ev.key.keysym.sym <= SDLK_F12) && ev.key.keysym.sym != SDLK_TAB) continue; // menu open: keys drive the menu
      switch(ev.type) {
        case SDL_QUIT: running = 0; break;
        case SDL_CONTROLLERDEVICEADDED: pad_open_all(); break;
        case SDL_CONTROLLERDEVICEREMOVED:
          for(int i = 0; i < 4; i++) if(pads[i] && !SDL_GameControllerGetAttached(pads[i])) { SDL_GameControllerClose(pads[i]); pads[i] = NULL; }
          break;
        case SDL_KEYDOWN: case SDL_KEYUP: {
          int down = ev.type == SDL_KEYDOWN;
          SDL_Keycode k = ev.key.keysym.sym;
          for(int i = 0; i < 12; i++) if(cfg.keys[i] == k) { if(down) keyState |= 1 << i; else keyState &= ~(1 << i); }
          if(k == SDLK_TAB) turboHeld = down;
          if(!down || ev.key.repeat) break;
          if(k == SDLK_F11 || (k == SDLK_RETURN && (ev.key.keysym.mod & KMOD_ALT))) {
            cfg.fullscreen = !cfg.fullscreen; APPLY_VIDEO(); config_save();
            for(int i = 0; i < 12; i++) if(cfg.keys[i] == SDLK_RETURN) keyState &= ~(1 << i);
          }
          if(k == SDLK_F5) { char t[64]; snprintf(t, sizeof t, state_io(snes, slot, 1) ? "Saved state %d" : "Couldn't save state %d", slot); menu_notify(t); }
          if(k == SDLK_F7) { char t[64]; snprintf(t, sizeof t, state_io(snes, slot, 0) ? "Loaded state %d" : "No state in slot %d", slot); menu_notify(t); }
          if(k == SDLK_F6 || k == SDLK_F8) { slot = (slot + (k == SDLK_F8 ? 1 : 8)) % 10; if(!slot && k == SDLK_F8) slot = 1; if(!slot) slot = 9; char t[64]; snprintf(t, sizeof t, "State slot %d", slot); menu_notify(t); }
          if(k == SDLK_PAUSE || k == SDLK_p) { paused = !paused; menu_notify(paused ? "Paused" : "Resumed"); }
          if(k == SDLK_F3) { turboToggle = !turboToggle; char t[64]; snprintf(t, sizeof t, "Fast-forward x%d", cfg.turbo); menu_notify(turboToggle ? t : "Normal speed"); }
          if(k == SDLK_F2) { cfg.aspect43 = !cfg.aspect43; APPLY_VIDEO(); config_save(); menu_notify(cfg.aspect43 ? "TV shape (4:3)" : "Square pixels"); }
          if(k == SDLK_F4) { cfg.widescreen = !cfg.widescreen; APPLY_VIDEO(); config_save(); menu_notify(cfg.widescreen ? "Widescreen on" : "Widescreen off"); }
          break;
        }
      }
    }
    uint64_t now = SDL_GetPerformanceCounter();
    acc += (double)(now - last) / freq; last = now;
    if(acc > 0.25) acc = 0.25;
    // fast-forward: the game runs `speed` frames per real frame; the sound chip keeps real time
    vpad_step();
    uint16_t padNow = pad_poll();
    if(getenv("FE4_PADLOG")) { static uint16_t last; if(padNow != last) printf("pad -> SNES mask %03X\n", padNow); last = padNow; }
    if(menu_visible()) { padNow = 0; padTurbo = 0; }
    int wantSpeed = forceSpeed > 1 ? forceSpeed : ((turboHeld || turboToggle || padTurbo) ? cfg.turbo : 1);
    if(forceSpeed <= 1) {
      int a = 1;
      if(textRecent && cfg.ffText > a) a = cfg.ffText;
      if(inBattle && cfg.ffBattle > a) a = cfg.ffBattle;
      if(otherPhase && cfg.ffEnemy > a) a = cfg.ffEnemy;
      // cursor: a direction held on the map during the player's phase (not in text or battle)
      if(((keyState | padNow) & 0xF0) && !otherPhase && !inBattle && !textRecent && cfg.ffCursor > a) a = cfg.ffCursor;
      if(a > wantSpeed) wantSpeed = a;
      static int lastA = 1;
      if(a != lastA && getenv("FE4_SPEEDLOG")) printf("frame %d: auto speed %d (text %d battle %d phase %d)\n", frame, a, textRecent > 0, inBattle, otherPhase);
      lastA = a;
    }
    if(wantSpeed != speed) { speed = wantSpeed; snes_setApuScale(snes, 1.0 / speed); }
    int toRun = 0;
    int turbo = turboUntil && frame < turboUntil;
    if(fast) toRun = 1;
    else while(acc >= frameTime - 0.002) { acc -= frameTime; toRun++; }
    int due = toRun;
    toRun *= speed;
    if(turbo) { // as many frames as fit in ~30 ms, then show one; no sound
      uint64_t t0 = SDL_GetPerformanceCounter(); int n = 0;
      while(frame + n < turboUntil && (double)(SDL_GetPerformanceCounter() - t0) / freq < 0.03) {
        snes->ppu->skipRender = (n % 8) != 7;
        uint16_t m = movieArg ? movie_mask(frame + n) : 0;
        for(int b = 0; b < 12; b++) snes_setButtonState(snes, 1, b, (m >> b) & 1);
        frzFrame = frame + n;
        if(recompiled) rc_runFrame(snes); else snes_runFrame(snes);
        n++;
      }
      frame += n; toRun = 0; due = 1;
      snes->apu->dsp->sampleCount = 0;
      { char t[128]; snprintf(t, sizeof t, "%s - getting the battle ready... %d%%", titleArg ? titleArg : "preview", frame * 100 / turboUntil); set_title(win, t); }
      if(frame >= turboUntil) {
        set_title(win, NULL); acc = 0;
        if(loopAt || stateCache) { loopLen = snes_saveState(snes, NULL); loopState = malloc(loopLen); snes_saveState(snes, loopState); }
        if(stateCache) { uint8_t* d = malloc(loopLen + 4); *(int*)d = turboUntil; memcpy(d + 4, loopState, loopLen); write_file(stateCache, d, loopLen + 4); free(d); }
        if(!loopAt) { free(loopState); loopState = NULL; }
      }
    }
    if(loopAt && loopState && frame >= loopAt) { snes_loadState(snes, loopState, loopLen); frame = turboUntil; }
    if(paused || (menu_visible() && cfg.pauseInMenu)) toRun = 0;
    for(int f = 0; f < toRun && running; f++) {
      uint16_t m = keyState | padNow;
      if(movieArg) m = movie_mask(frame);
      for(int b = 0; b < 12; b++) snes_setButtonState(snes, 1, b, (m >> b) & 1);
      frzFrame = frame;
      snes->ppu->skipRender = f != toRun - 1; // only draw the frame that will be shown
      if(recompiled) rc_runFrame(snes); else snes_runFrame(snes);
      frame++;
      { const uint8_t* r = snes->ram;
        uint32_t tp = r[0x186A] | r[0x186B] << 8 | r[0x186C] << 16;
        if(tp != lastTextPtr) { lastTextPtr = tp; textRecent = 12; } else if(textRecent) textRecent--;
        inBattle = (r[0xD7] | r[0xD8] << 8) == 0xC144;
        otherPhase = r[0xD91] != 0; }
      if(frame % 120 == 0) sram_flush(snes);
      if(maxFrames && frame >= maxFrames) running = 0;
    }
    snes->ppu->skipRender = false;
    // audio: hand over exactly what the sound chip produced (32040 Hz) resampled to 48 kHz
    if(toRun && (dev || wav)) {
      double wantOut = snes->apu->dsp->sampleCount * (48000.0 / 32040.0) + audioCarry;
      int out = (int)wantOut; audioCarry = wantOut - out;
      if(out > 8192) out = 8192;
      if(out > 0) {
        snes_setSamples(snes, abuf, out);
        int queue = dev && SDL_GetQueuedAudioSize(dev) <= 48000 * 4 / 10;
        // music folder tracks play along with what is heard (the game's sound option "off" silences them too)
        if(queue || wav) music_mix(abuf, out, (snes->ram[0x4EA] & 0x10) ? 0 : cfg.musicVolume);
        int vol = cfg.mute ? 0 : cfg.volume;
        if(vol < 100) for(int i = 0; i < out * 2; i++) abuf[i] = abuf[i] * vol / 100;
        if(queue) SDL_QueueAudio(dev, abuf, out * 4);
        if(wav) { fwrite(abuf, 4, out, wav); wavBytes += out * 4; }
      }
    }
    if(toRun || fast) {
      snes_setPixels(snes, px);
      SDL_UpdateTexture(tex, NULL, px + 16 * 2048, 2048);
      if(wideOn) SDL_UpdateTexture(wtex, NULL, wideBuf, FE4WIDE_W * 4);
      if(shotDir && shotEvery && frame % shotEvery < toRun) { // debug: periodic screenshots
        char p[1200]; snprintf(p, sizeof p, "%s/s%06d.bmp", shotDir, frame);
        SDL_Surface* sf = SDL_CreateRGBSurfaceWithFormat(0, 256, 224, 32, SDL_PIXELFORMAT_ARGB8888);
        for(int y = 0; y < 224; y++) for(int x = 0; x < 256; x++)
          ((uint32_t*)sf->pixels)[y * (sf->pitch / 4) + x] = ((uint32_t*)px)[(16 + y * 2) * 512 + x * 2] | 0xff000000;
        SDL_SaveBMP(sf, p); SDL_FreeSurface(sf);
      }
    }
    fpsFrames += toRun;
    if(fast ? (!running || frame % 60 == 0) : (due || cfg.vsync || !running)) {
      if(ms.randoBusy) {
        int r = kit_rando_poll();
        if(r == 2 || r == -1) {
          ms.randoBusy = 0;
          char p[1200], q[1200];
          snprintf(p, sizeof p, "%srando_in.smc", cacheDir); remove(p);
          snprintf(p, sizeof p, "%srando_out.smc", cacheDir); remove(p);
          snprintf(p, sizeof p, "%srando_out_spoiler.txt", cacheDir);
          snprintf(q, sizeof q, "%s%s spoiler.txt", mods_dir(), randoName);
          if(r == 2) { remove(q); rename(p, q); }
          snprintf(q, sizeof q, "%s.ips", randoName);
          char full[1300]; snprintf(full, sizeof full, "%s%s", mods_dir(), q);
          if(r == 2 && file_exists(full)) {
            mods_rescan(); mods_add_first_run(q, 1); mods_save();
            ms.randoDone = 1;
            snprintf(ms.randoMsg, sizeof ms.randoMsg, "Done: \"%s\" is now in your mods (the other randomizer seeds are switched off). "
              "Restart to play it; it starts from a new game with its own save file.", q);
            menu_notify("Randomized game ready");
          } else snprintf(ms.randoMsg, sizeof ms.randoMsg, "%s", r == 2 ? "The randomizer finished but made no patch." : kit_error());
        }
      }
      // menu: gather info, build UI, handle what was clicked
      for(int i = 1; i <= 9; i++) state_info(i, &ms.slotUsed[i], ms.slotTime[i], sizeof ms.slotTime[i]);
      if(menu_visible()) {
        CheatUnit army[64]; ms.armyCount = cheat_army(snes->ram, snes->cart->rom, romLen, army, 64);
        ms.armyHurt = 0; for(int i = 0; i < ms.armyCount; i++) if(army[i].hp < army[i].maxHp) ms.armyHurt++;
        ms.selOk = cheat_selected(snes->ram, snes->cart->rom, romLen, &ms.sel);
      }
      ms.padCount = 0; for(int i = 0; i < 4; i++) if(pads[i]) ms.padCount++;
      ms.fps = fps; ms.speed = speed; ms.compiledBlocks = rc_stats.blocks; ms.interpOps = rc_stats.interp; ms.wideActive = wideOn;
      ms.musicTracks = music_count(); ms.musicNow = music_playing(); ms.musicReq = music_last_request();
      ms.musicNowFile = music_file(ms.musicNow); ms.musicReqFile = music_file(ms.musicReq);
      int act = menu_frame(&ms);
      if(act & MA_SAVE_STATE) { char t[64]; snprintf(t, sizeof t, state_io(snes, slot, 1) ? "Saved state %d" : "Couldn't save state %d", slot); menu_notify(t); }
      if(act & MA_LOAD_STATE) { char t[64]; snprintf(t, sizeof t, state_io(snes, slot, 0) ? "Loaded state %d" : "No state in slot %d", slot); menu_notify(t); }
      if(act & MA_RESET) { snes_reset(snes, false); music_stop(); menu_notify("Reset"); }
      if(act & (MA_MUSIC_RESCAN | MA_MUSIC_TOGGLE)) {
        if(act & MA_MUSIC_RESCAN) music_rescan();
        music_set_enabled(cfg.customMusic);
        // ask for the current song again, so it switches between the file and the game's own music now
        int s = music_last_request();
        if(s && musicPatched) { snes->ram[0x4BA] = (uint8_t)s; snes->ram[0x4BB] = 0; snes->ram[0x4C6] = 0; snes->ram[0x4C7] = 0; }
        if(act & MA_MUSIC_RESCAN) { char t[80]; snprintf(t, sizeof t, "%d track%s in the music folder", music_count(), music_count() == 1 ? "" : "s"); menu_notify(t); }
      }
      if(act & MA_MUSIC_FOLDER) { char u[1200]; snprintf(u, sizeof u, "file:///%s", music_dir()); for(char* q = u; *q; q++) if(*q == '\\') *q = '/'; SDL_OpenURL(u); }
      if(act & MA_QUIT) running = 0;
      if(act & MA_RESTART) { running = 0; restartAfter = 1; }
      if(act & MA_RANDOMIZE) {
        // input: your ROM with the mods that are switched on, except other randomizer seeds
        // (in the same copier-header form as your ROM file)
        char in[1200], ips[1200]; snprintf(in, sizeof in, "%srando_in.smc", cacheDir);
        int ok = 0, plainLen = 0; uint8_t* plain = read_file(romPath, &plainLen);
        if(plain && (plainLen & 0x7fff) == 0x200) { memmove(plain, plain + 512, plainLen - 512); plainLen -= 512; }
        if(plain && mods_apply_to(&plain, &plainLen, romHdr, romHadHdr, 1) >= 0) {
          FILE* f = fopen(in, "wb");
          ok = f && (!romHadHdr || fwrite(romHdr, 1, 512, f) == 512) && fwrite(plain, 1, plainLen, f) == (size_t)plainLen;
          if(f) fclose(f);
        }
        free(plain);
        snprintf(randoName, sizeof randoName, "Randomizer %s %lld", ms.randoPreset, ms.randoSeed);
        snprintf(ips, sizeof ips, "%s%s.ips", mods_dir(), randoName);
        ms.randoDone = 0; ms.randoMsg[0] = 0;
        if(ok && kit_rando_start(in, ips, NULL, ms.randoSeed, ms.randoPreset, ms.randoKeys, ms.randoVals, ms.randoN)) ms.randoBusy = 1;
        else snprintf(ms.randoMsg, sizeof ms.randoMsg, "Couldn't start the randomizer: %s", ok ? kit_error() : "couldn't write a temporary file");
      }
      if(act & MA_KEYS_DEFAULT) { for(int i = 0; i < 12; i++) cfg.keys[i] = SDL_GetKeyFromName(BTN_DEFKEYS[i]); menu_notify("Default keys"); }
      if(act & MA_CHEAT) {
        int n = cheat_apply(snes->ram, snes->cart->rom, romLen, ms.cheatWhat, ms.cheatAll);
        static const char* what[] = { "", "HP restored", "Gold set to 50,000", "EXP set to 99" };
        char t[96]; snprintf(t, sizeof t, "%s (%d unit%s)", what[ms.cheatWhat], n, n == 1 ? "" : "s"); menu_notify(t);
      }
      if(act & MA_PAD_DEFAULT) { memcpy(cfg.pad, PAD_DEFAULTS, sizeof cfg.pad); menu_notify("Default gamepad buttons"); }
      if(act & MA_VIDEO) APPLY_VIDEO();
      if(act & MA_SAVE_CONFIG) { set_rom_flags(snes); config_save(); }
      // game picture, letterboxed to its shape
      int ow, oh; SDL_GetRendererOutputSize(ren, &ow, &oh);
      double aspect = (double)LOGICAL_W / 448.0;
      SDL_Rect dst; dst.h = oh; dst.w = (int)(oh * aspect + 0.5);
      if(dst.w > ow) { dst.w = ow; dst.h = (int)(ow / aspect + 0.5); }
      dst.x = (ow - dst.w) / 2; dst.y = (oh - dst.h) / 2;
      SDL_SetRenderDrawColor(ren, 0, 0, 0, 255);
      SDL_RenderClear(ren);
      SDL_RenderCopy(ren, wideOn ? wtex : tex, NULL, &dst);
      menu_render();
      SDL_RenderPresent(ren);
    }
    Uint32 tnow = SDL_GetTicks();
    if(tnow - fpsT0 >= 500) { fps = fpsFrames * 1000.0f / (tnow - fpsT0); fpsFrames = 0; fpsT0 = tnow; }
    if(!toRun && !cfg.vsync) SDL_Delay(1);
  }
  if(shotArg && wideOn) {
    SDL_Surface* s = SDL_CreateRGBSurfaceWithFormat(0, FE4WIDE_W, 224, 32, SDL_PIXELFORMAT_ARGB8888);
    for(int y = 0; y < 224; y++) for(int x = 0; x < FE4WIDE_W; x++)
      ((uint32_t*)s->pixels)[y * (s->pitch / 4) + x] = wideBuf[y * FE4WIDE_W + x] | 0xff000000;
    SDL_SaveBMP(s, shotArg); SDL_FreeSurface(s); shotArg = NULL;
  }
  if(shotArg) {
    snes_setPixels(snes, px);
    SDL_Surface* s = SDL_CreateRGBSurfaceWithFormat(0, 256, 224, 32, SDL_PIXELFORMAT_ARGB8888);
    for(int y = 0; y < 224; y++) for(int x = 0; x < 256; x++)
      ((uint32_t*)s->pixels)[y * (s->pitch / 4) + x] = ((uint32_t*)px)[(16 + y * 2) * 512 + x * 2] | 0xff000000;
    SDL_SaveBMP(s, shotArg); SDL_FreeSurface(s);
  }
  if(wav) { // finish the RIFF header: 48 kHz stereo 16-bit
    uint32_t h[11] = { 0x46464952, 36 + wavBytes, 0x45564157, 0x20746d66, 16, 0x00020001, 48000, 48000 * 4, 0x00100004, 0x61746164, wavBytes };
    fseek(wav, 0, SEEK_SET); fwrite(h, 4, 11, wav); fclose(wav);
  }
  sram_flush(snes);
  if(rc_recordMisses) save_learned();
  printf("frames %d; compiled blocks %llu, interpreted ops %llu\n", frame, rc_stats.blocks, rc_stats.interp);
  config_save();
  menu_shutdown();
  if(dev) SDL_CloseAudioDevice(dev);
  rc_jitFree(jitHandle);
  snes_free(snes);
  SDL_Quit();
  fflush(stdout); fflush(stderr);
  if(restartAfter) { // start a fresh copy of the program (same ROM / test play) and end this one
#ifdef _WIN32
    char exe[1100]; GetModuleFileNameA(NULL, exe, sizeof exe);
    char cmd[2600]; snprintf(cmd, sizeof cmd, testPlay ? "\"%s\" --play \"%s\"" : "\"%s\"", exe, romPath);
    STARTUPINFOA si; memset(&si, 0, sizeof si); si.cb = sizeof si; PROCESS_INFORMATION pi;
    if(CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) { CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
#else
    char* av[4] = { argv[0], testPlay ? "--play" : NULL, testPlay ? romPath : NULL, NULL };
    char self[1100]; ssize_t n = readlink("/proc/self/exe", self, sizeof self - 1);
    if(n > 0) { self[n] = 0; execv(self, av); }
#endif
  }
#ifdef _WIN32
  // everything is saved; end the process here rather than running DLL teardown
  TerminateProcess(GetCurrentProcess(), 0);
#endif
  return 0;
}
