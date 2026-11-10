// In-game settings menu (Dear ImGui). C interface for the frontend.
#ifndef FE4_MENU_H
#define FE4_MENU_H
#include <SDL.h>
#include "cheats.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct MenuState {
  // settings the menu edits directly (the frontend applies them when MA_VIDEO etc. is returned)
  int* widescreen;   int* aspect43;  int* smooth;  int* vsync;  int* fullscreen;  int* scale;
  int* volume;       int* mute;      int* turbo;   int* ffToggle; int* hoverstats; int* pauseInMenu;
  int* showFps;      int* paused;    int* slot;
  int* ffText; int* ffBattle; int* ffEnemy; int* ffCursor;   // automatic speed-ups, 1 = off
  SDL_Keycode* keys;                 // 12 keyboard bindings, SNES order B Y Select Start Up Down Left Right A X L R
  int* pad;          int padCount;   // gamepad bindings (padmap.h), number of pads connected
  // information shown by the menu
  int slotUsed[10];  char slotTime[10][32];
  float fps;         int speed;
  int recompiled;    unsigned long long compiledBlocks, interpOps;
  int hoverActive;   int wideActive;
  const char* version; const char* romName; const char* romInfo;
  // mods / randomizer
  int testPlay;                      // --play session: mods are off
  int modsApplied;
  int randoBusy;                     // the kit is randomizing
  int randoDone;                     // 1: a new seed was added to the mods (randoMsg says which)
  char randoMsg[600];                // result or error of the last run
  // filled by the menu with MA_RANDOMIZE
  char randoPreset[24]; long long randoSeed; int randoN;
  const char* randoKeys[64]; const char* randoVals[64];
  // cheats: the player's units right now (filled while the menu is open)
  int armyCount; int armyHurt; int selOk; CheatUnit sel;
  int cheatWhat, cheatAll;           // filled by the menu with MA_CHEAT
} MenuState;

enum {
  MA_SAVE_STATE = 1 << 0, MA_LOAD_STATE = 1 << 1, MA_RESET = 1 << 2, MA_QUIT = 1 << 3,
  MA_VIDEO = 1 << 4,       // widescreen / aspect / smooth / vsync / fullscreen / scale changed
  MA_SAVE_CONFIG = 1 << 5, // any setting changed: write fe4port.ini
  MA_KEYS_DEFAULT = 1 << 6,
  MA_RESTART = 1 << 7,      // restart the game (to apply mods)
  MA_RANDOMIZE = 1 << 8,    // run the kit's randomizer with randoPreset / randoSeed / randoKeys
  MA_PAD_DEFAULT = 1 << 9,  // gamepad bindings back to default
  MA_CHEAT = 1 << 10        // apply cheatWhat to the selected unit or (cheatAll) every unit of the army
};

void menu_init(SDL_Window* win, SDL_Renderer* ren);
void menu_shutdown(void);
int  menu_event(const SDL_Event* ev, MenuState* st); // 1 = the menu used this event (don't pass it to the game)
int  menu_frame(MenuState* st);                      // build the UI for this frame; returns MA_* bits
void menu_render(void);
int  menu_visible(void);
void menu_toggle(void);
int  menu_popup_open(void);                          // a menu or window of the menu is open (Esc closes that first)
int  menu_capturing_key(void);                       // waiting for a key to bind
void menu_notify(const char* text);                  // short message in the corner
#ifdef __cplusplus
}
#endif
#endif
