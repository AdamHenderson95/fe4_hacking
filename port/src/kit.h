// fe4kit from inside the port: find the kit, read its randomizer options, run the randomizer.
#ifndef FE4_KIT_H
#define FE4_KIT_H
#ifdef __cplusplus
extern "C" {
#endif

#define KIT_MAXOPT 64
typedef struct KitOption {
  char key[32], label[96], help[256];
  int isInt;                 // 1: number between lo and hi; 0: one of choices
  int lo, hi;
  char choices[8][24]; int nchoices;
  char def[24];
} KitOption;
typedef struct KitPreset { char name[24]; char kv[KIT_MAXOPT][2][24]; int n; } KitPreset;

int  kit_init(const char* baseDir, const char* cacheDir); // 1 = kit found
int  kit_found(void);
const char* kit_where(void);       // the kit program used (for the menu)
int  kit_options(KitOption** opts, KitPreset** presets, int* npresets); // loads once; returns option count (0 = not available)
const char* kit_error(void);       // last problem, for the menu

// randomize: inRom = ROM file to start from (written by the caller), outIps/outSpoiler = where the
// results go. Runs in the background; poll with kit_rando_poll.
int  kit_rando_start(const char* inRom, const char* outIps, const char* outSpoiler, long long seed,
                     const char* preset, const char* const* keys, const char* const* vals, int n);
int  kit_rando_poll(void);         // 1 running, 0 idle, 2 finished OK (once), -1 failed (once; see kit_error)
const char* kit_rando_log(void);   // what the kit printed

#ifdef __cplusplus
}
#endif
#endif
