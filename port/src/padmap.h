// Gamepad bindings: which controller input presses each SNES button (and fast-forward).
// Values are SDL_GameControllerButton numbers, or PAD_LT / PAD_RT for the analog triggers, or -1 (none).
#ifndef FE4_PADMAP_H
#define FE4_PADMAP_H
#include <SDL.h>
#include <string.h>

#define PAD_LT 100
#define PAD_RT 101
#define PAD_FF 12          // index of the fast-forward binding after the 12 SNES buttons
#define PAD_BINDINGS 13

// SNES order: B Y Select Start Up Down Left Right A X L R, then fast-forward.
// Default: Nintendo layout by position (bottom = B, right = A, left = Y, top = X), right trigger = fast-forward.
static const int PAD_DEFAULTS[PAD_BINDINGS] = {
  SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_START,
  SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
  SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
  PAD_RT
};

// name used in fe4port.ini
static inline const char* pad_input_id(int v) {
  if(v == PAD_LT) return "lefttrigger";
  if(v == PAD_RT) return "righttrigger";
  if(v < 0) return "none";
  const char* s = SDL_GameControllerGetStringForButton((SDL_GameControllerButton)v);
  return s ? s : "none";
}
static inline int pad_input_from_id(const char* s) {
  if(!strcmp(s, "lefttrigger")) return PAD_LT;
  if(!strcmp(s, "righttrigger")) return PAD_RT;
  if(!strcmp(s, "none")) return -1;
  SDL_GameControllerButton b = SDL_GameControllerGetButtonFromString(s);
  return b == SDL_CONTROLLER_BUTTON_INVALID ? -2 : (int)b;
}
// name shown in the menu (by position, since controllers label their buttons differently)
static inline const char* pad_input_label(int v) {
  switch(v) {
    case SDL_CONTROLLER_BUTTON_A: return "Bottom button (Xbox A, PS Cross)";
    case SDL_CONTROLLER_BUTTON_B: return "Right button (Xbox B, PS Circle)";
    case SDL_CONTROLLER_BUTTON_X: return "Left button (Xbox X, PS Square)";
    case SDL_CONTROLLER_BUTTON_Y: return "Top button (Xbox Y, PS Triangle)";
    case SDL_CONTROLLER_BUTTON_BACK: return "Back / View / Select";
    case SDL_CONTROLLER_BUTTON_START: return "Start / Menu / Options";
    case SDL_CONTROLLER_BUTTON_GUIDE: return "Guide / Home";
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return "Left stick click";
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return "Right stick click";
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return "Left shoulder";
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return "Right shoulder";
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return "D-pad up";
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return "D-pad down";
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return "D-pad left";
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return "D-pad right";
    case SDL_CONTROLLER_BUTTON_MISC1: return "Share / Capture";
    case SDL_CONTROLLER_BUTTON_TOUCHPAD: return "Touchpad click";
    case PAD_LT: return "Left trigger";
    case PAD_RT: return "Right trigger";
    case -1: return "(none)";
    default: return "Other button";
  }
}
static inline int pad_input_down(SDL_GameController* g, int v) {
  if(v == PAD_LT) return SDL_GameControllerGetAxis(g, SDL_CONTROLLER_AXIS_TRIGGERLEFT) > 16000;
  if(v == PAD_RT) return SDL_GameControllerGetAxis(g, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) > 16000;
  if(v < 0) return 0;
  return SDL_GameControllerGetButton(g, (SDL_GameControllerButton)v);
}
#endif
