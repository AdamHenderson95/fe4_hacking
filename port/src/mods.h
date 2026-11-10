// Mods: .ips / .bps patches in the mods folder, applied to the ROM at startup in load order.
#ifndef FE4_MODS_H
#define FE4_MODS_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct ModInfo {
  char file[256];      // file name inside the mods folder
  int enabled;         // in the saved load order
  int randomizer;      // made by the port's randomizer (only one of these is on at a time)
  int state;           // this session: 0 not applied, 1 applied, -1 failed
  char note[192];      // why it failed, or a remark ("made for a ROM with a copier header")
} ModInfo;

void mods_init(const char* dir);          // dir ends with a slash; creates it, scans it, reads load_order.txt
void mods_rescan(void);                    // pick up added / removed files (keeps on/off and order)
int  mods_count(void);
ModInfo* mods_at(int i);
void mods_move(int i, int delta);          // reorder
void mods_set(int i, int on);              // on/off (turning a randomizer seed on turns the others off)
void mods_save(void);                      // write load_order.txt
int  mods_changed(void);                   // the saved set differs from what this session applied
const char* mods_dir(void);
int  mods_add_first_run(const char* file, int on); // register a new file (e.g. a new randomizer seed) at the end

// Apply the enabled mods to a headerless ROM image (realloc'd if a patch grows it).
// hdr/hadHdr: the copier header the user's ROM file had, if any (IPS patches made for the
// headered file are detected). Returns the number applied; failures are marked in state/note.
int  mods_apply(uint8_t** rom, int* len, const uint8_t* hdr, int hadHdr);
// the same with the mods switched on now, without touching the session's state (randomizer input);
// -1 if one of them fails
int  mods_apply_to(uint8_t** rom, int* len, const uint8_t* hdr, int hadHdr, int skipRandomizer);
int  mods_applied(void);                   // how many were applied this session
uint32_t mods_set_hash(void);              // hash of the applied file names (0 = none): names the save files

#ifdef __cplusplus
}
#endif
#endif
