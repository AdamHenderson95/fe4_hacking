// In-game settings menu, in the spirit of Ship of Harkinian's menu bar.
// F1 / Esc / right stick click opens it; settings apply immediately and are saved to fe4port.ini.
#include <stdio.h>
#include <string.h>
#include "imgui.h"
#include "imgui_internal.h" // to put keyboard/gamepad focus on the menu bar when it opens
#include "imgui_impl_sdl2.h"
#include "imgui_impl_sdlrenderer2.h"
#include "menu.h"
#include "mods.h"
#include "kit.h"
#include "padmap.h"
#include <stdlib.h>
#include <time.h>
#include "font_roboto.inc"

static SDL_Window* gWin;
static SDL_Renderer* gRen;
static bool visible = false;
static int bindingFor = -1;          // SNES button waiting for a key, or -1
static int padBindingFor = -1; static int bindPadSaved;       // binding (SNES button or PAD_FF) waiting for a gamepad button, or -1
static char toast[128]; static Uint32 toastUntil;
static bool showAbout = false, showControls = false, showMods = false, showRando = false;
static float baseFont = 18.0f;

static const char* BTN_LABELS[12] = { "B", "Y", "Select", "Start", "Up", "Down", "Left", "Right", "A", "X", "L", "R" };

extern "C" void menu_init(SDL_Window* win, SDL_Renderer* ren) {
  gWin = win; gRen = ren;
  IMGUI_CHECKVERSION();
  ImGui::CreateContext();
  ImGuiIO& io = ImGui::GetIO();
  io.IniFilename = NULL; // layout isn't saved; settings live in fe4port.ini
  io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
  ImFontConfig fc; fc.OversampleH = 2;
  io.Fonts->AddFontFromMemoryCompressedTTF(roboto_compressed_data, roboto_compressed_size, 36.0f, &fc);
  ImGui::StyleColorsDark();
  ImGuiStyle& s = ImGui::GetStyle();
  s.WindowRounding = 6; s.FrameRounding = 4; s.PopupRounding = 4; s.GrabRounding = 4;
  s.WindowPadding = ImVec2(12, 10); s.ItemSpacing = ImVec2(10, 7); s.FramePadding = ImVec2(8, 4);
  // a dark blue/gold palette that sits well next to FE4's menus
  ImVec4* c = s.Colors;
  c[ImGuiCol_WindowBg] = ImVec4(0.07f, 0.09f, 0.16f, 0.98f);
  c[ImGuiCol_PopupBg] = ImVec4(0.07f, 0.09f, 0.16f, 0.98f);
  c[ImGuiCol_MenuBarBg] = ImVec4(0.09f, 0.12f, 0.22f, 0.97f);
  c[ImGuiCol_Header] = ImVec4(0.20f, 0.28f, 0.50f, 0.80f);
  c[ImGuiCol_HeaderHovered] = ImVec4(0.27f, 0.37f, 0.64f, 0.90f);
  c[ImGuiCol_HeaderActive] = ImVec4(0.32f, 0.44f, 0.74f, 1.00f);
  c[ImGuiCol_CheckMark] = ImVec4(0.96f, 0.80f, 0.36f, 1.00f);
  c[ImGuiCol_SliderGrab] = ImVec4(0.96f, 0.80f, 0.36f, 0.85f);
  c[ImGuiCol_SliderGrabActive] = ImVec4(1.00f, 0.86f, 0.45f, 1.00f);
  c[ImGuiCol_FrameBg] = ImVec4(0.14f, 0.18f, 0.30f, 0.90f);
  c[ImGuiCol_FrameBgHovered] = ImVec4(0.20f, 0.26f, 0.42f, 0.90f);
  c[ImGuiCol_Button] = ImVec4(0.20f, 0.28f, 0.50f, 0.85f);
  c[ImGuiCol_ButtonHovered] = ImVec4(0.27f, 0.37f, 0.64f, 1.00f);
  c[ImGuiCol_Separator] = ImVec4(0.96f, 0.80f, 0.36f, 0.30f);
  c[ImGuiCol_Text] = ImVec4(0.93f, 0.93f, 0.96f, 1.00f);
  c[ImGuiCol_TextDisabled] = ImVec4(0.60f, 0.63f, 0.72f, 1.00f);
  ImGui_ImplSDL2_InitForSDLRenderer(win, ren);
  ImGui_ImplSDLRenderer2_Init(ren);
}

extern "C" void menu_shutdown(void) {
  ImGui_ImplSDLRenderer2_Shutdown();
  ImGui_ImplSDL2_Shutdown();
  ImGui::DestroyContext();
}

extern "C" int menu_visible(void) { return visible; }
static bool focusBar;
extern "C" void menu_toggle(void) { visible = !visible; bindingFor = padBindingFor = -1; focusBar = visible; }
extern "C" int menu_popup_open(void) {
  return visible && (ImGui::IsPopupOpen("", ImGuiPopupFlags_AnyPopupId | ImGuiPopupFlags_AnyPopupLevel) || showControls || showAbout || showMods || showRando);
}
extern "C" int menu_capturing_key(void) { return bindingFor >= 0 || padBindingFor >= 0; }
extern "C" void menu_notify(const char* text) {
  snprintf(toast, sizeof toast, "%s", text);
  toastUntil = SDL_GetTicks() + 2200;
}

static void set_pad_binding(MenuState* st, int v) {
  for(int i = 0; i < PAD_BINDINGS; i++) if(st->pad[i] == v && !(i >= 4 && i <= 7)) st->pad[i] = -1; // one button, one job
  st->pad[padBindingFor] = v;
  char t[128]; snprintf(t, sizeof t, "%s = %s", padBindingFor == PAD_FF ? "Fast-forward" : BTN_LABELS[padBindingFor], pad_input_label(v)); menu_notify(t);
  padBindingFor = -1;
  ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;
}

extern "C" int menu_event(const SDL_Event* ev, MenuState* st) {
  if(padBindingFor >= 0) {
    if(ev->type == SDL_CONTROLLERBUTTONDOWN) { set_pad_binding(st, ev->cbutton.button); bindPadSaved = 1; return 1; }
    if(ev->type == SDL_CONTROLLERAXISMOTION && ev->caxis.value > 16000 &&
       (ev->caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || ev->caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT)) {
      set_pad_binding(st, ev->caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT ? PAD_LT : PAD_RT); bindPadSaved = 1; return 1;
    }
    if(ev->type == SDL_KEYDOWN && ev->key.keysym.sym == SDLK_ESCAPE) { padBindingFor = -1; ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad; return 1; }
    if(ev->type == SDL_CONTROLLERBUTTONUP || ev->type == SDL_CONTROLLERAXISMOTION) return 1;
  }
  if(bindingFor >= 0 && ev->type == SDL_KEYDOWN && !ev->key.repeat) {
    if(ev->key.keysym.sym != SDLK_ESCAPE) {
      SDL_Keycode k = ev->key.keysym.sym;
      for(int i = 0; i < 12; i++) if(st->keys[i] == k) st->keys[i] = SDLK_UNKNOWN; // one key, one button
      st->keys[bindingFor] = k;
      char t[96]; snprintf(t, sizeof t, "%s = %s", BTN_LABELS[bindingFor], SDL_GetKeyName(k)); menu_notify(t);
    }
    bindingFor = -1;
    return 1;
  }
  if(visible && ev->type == SDL_KEYDOWN && ev->key.keysym.sym == SDLK_ESCAPE && (showControls || showAbout || showMods || showRando) &&
     !ImGui::IsPopupOpen("", ImGuiPopupFlags_AnyPopupId | ImGuiPopupFlags_AnyPopupLevel)) { showControls = showAbout = showMods = showRando = false; return 1; }
  ImGui_ImplSDL2_ProcessEvent(ev);
  if(!visible) return 0;
  ImGuiIO& io = ImGui::GetIO();
  if((ev->type == SDL_KEYDOWN || ev->type == SDL_KEYUP) && io.WantCaptureKeyboard) return 1;
  if((ev->type == SDL_MOUSEBUTTONDOWN || ev->type == SDL_MOUSEWHEEL) && io.WantCaptureMouse) return 1;
  return 0;
}

static void help_marker(const char* text) { // tooltip for the item just drawn (hover it to read)
  if(ImGui::BeginItemTooltip()) { ImGui::PushTextWrapPos(ImGui::GetFontSize() * 24); ImGui::TextUnformatted(text); ImGui::PopTextWrapPos(); ImGui::EndTooltip(); }
}

static bool check(const char* label, int* v, const char* shortcut = NULL) {
  bool b = *v != 0;
  bool changed = ImGui::MenuItem(label, shortcut, &b);
  if(changed) *v = b;
  return changed;
}

static void open_path(const char* p) { // a folder or file in the system's file browser / text viewer
  char url[1400]; snprintf(url, sizeof url, "file:///%s", p[0] == '/' ? p + 1 : p);
  for(char* c = url; *c; c++) if(*c == '\\') *c = '/';
  SDL_OpenURL(url);
}

static void restart_button(MenuState* st, int* act) {
  ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0.55f, 0.42f, 0.12f, 1.0f));
  ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4(0.70f, 0.54f, 0.16f, 1.0f));
  if(ImGui::Button("Restart the game with these mods")) *act |= MA_RESTART;
  ImGui::PopStyleColor(2);
  ImGui::SameLine(); ImGui::TextDisabled("(progress since your last save is lost)");
  (void)st;
}

static int mods_window(MenuState* st) {
  int act = 0;
  ImGui::SetNextWindowSize(ImVec2(baseFont * 34, baseFont * 20), ImGuiCond_Appearing);
  ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
  if(ImGui::Begin("Mods", &showMods, ImGuiWindowFlags_NoCollapse)) {
    ImGui::TextWrapped("Patches (.ips or .bps) in the mods folder change the game when it starts, applied from the top "
                       "of this list down. Hacks made with fe4kit, randomizer seeds and other FE4 patches all work.");
    if(st->testPlay) ImGui::TextColored(ImVec4(0.96f, 0.80f, 0.36f, 1), "Test play: mods are off for this session.");
    ImGui::Spacing();
    int n = mods_count(), changed = 0;
    if(!n) ImGui::TextDisabled("The mods folder is empty. Put .ips or .bps files in it, then press Refresh.");
    else if(ImGui::BeginTable("mods", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingStretchProp | ImGuiTableFlags_ScrollY,
                              ImVec2(0, ImGui::GetContentRegionAvail().y - ImGui::GetFrameHeightWithSpacing() * 2.6f))) {
      ImGui::TableSetupColumn("on", ImGuiTableColumnFlags_WidthFixed);
      ImGui::TableSetupColumn("name", ImGuiTableColumnFlags_WidthStretch);
      ImGui::TableSetupColumn("order", ImGuiTableColumnFlags_WidthFixed);
      for(int i = 0; i < n; i++) {
        ModInfo* m = mods_at(i);
        ImGui::PushID(i);
        ImGui::TableNextRow();
        ImGui::TableNextColumn();
        bool on = m->enabled != 0;
        if(ImGui::Checkbox("##on", &on)) { mods_set(i, on); changed = 1; }
        ImGui::TableNextColumn();
        ImGui::AlignTextToFramePadding();
        ImGui::TextUnformatted(m->file);
        if(m->state == 1) { ImGui::SameLine(); ImGui::TextColored(ImVec4(0.45f, 0.85f, 0.45f, 1), "  in use"); }
        else if(m->state == -1) { ImGui::SameLine(); ImGui::TextColored(ImVec4(1, 0.45f, 0.4f, 1), "  didn't apply"); }
        if(m->state == -1 && m->note[0]) { ImGui::TextDisabled("%s", m->note); }
        // spoiler log next to a randomizer seed
        if(m->randomizer) {
          char sp[400]; snprintf(sp, sizeof sp, "%s", m->file); char* d = strrchr(sp, '.'); if(d) *d = 0;
          strncat(sp, " spoiler.txt", sizeof sp - strlen(sp) - 1);
          char full[1400]; snprintf(full, sizeof full, "%s%s", mods_dir(), sp);
          FILE* f = fopen(full, "r");
          if(f) { fclose(f); ImGui::SameLine(); if(ImGui::SmallButton("spoiler log")) open_path(full); }
        }
        ImGui::TableNextColumn();
        ImGui::BeginDisabled(i == 0); if(ImGui::ArrowButton("##up", ImGuiDir_Up)) { mods_move(i, -1); changed = 1; } ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(i == n - 1); if(ImGui::ArrowButton("##dn", ImGuiDir_Down)) { mods_move(i, 1); changed = 1; } ImGui::EndDisabled();
        ImGui::PopID();
      }
      ImGui::EndTable();
    }
    if(changed) mods_save();
    if(ImGui::Button("Open the mods folder")) open_path(mods_dir());
    ImGui::SameLine(); if(ImGui::Button("Refresh")) { mods_rescan(); mods_save(); }
    ImGui::SameLine(); if(ImGui::Button("Randomizer...")) showRando = true;
    if(mods_changed() && !st->testPlay) restart_button(st, &act);
    else if(!st->testPlay) ImGui::TextDisabled(st->modsApplied ? "%d mod(s) in use. Saves for this set of mods are kept separately." : "No mods in use.", st->modsApplied);
  }
  ImGui::End();
  return act;
}

static int rando_window(MenuState* st) {
  int act = 0;
  static char vals[KIT_MAXOPT][24]; static int presetIdx = 1, inited = 0; static char seedText[24] = "";
  ImGui::SetNextWindowSize(ImVec2(baseFont * 30, baseFont * 24), ImGuiCond_Appearing);
  ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
  if(ImGui::Begin("Randomizer", &showRando, ImGuiWindowFlags_NoCollapse)) {
    KitOption* opts; KitPreset* pre; int npre;
    int n = kit_options(&opts, &pre, &npre);
    if(n < 0) { ImGui::TextUnformatted("Loading the randomizer's options from fe4kit..."); ImGui::End(); return 0; }
    if(n == 0) {
      ImGui::TextWrapped("The randomizer is part of fe4kit. Put BuilderOfTheHolyWar.exe next to FE4.exe (or in a folder called fe4kit "
                         "next to it), then open this window again.");
      if(kit_error()[0]) ImGui::TextDisabled("%s", kit_error());
      ImGui::End(); return 0;
    }
    auto apply_preset = [&](int p) {
      for(int i = 0; i < n; i++) snprintf(vals[i], 24, "%s", opts[i].def);
      if(p >= 0 && p < npre) for(int k = 0; k < pre[p].n; k++) for(int i = 0; i < n; i++)
        if(!strcmp(opts[i].key, pre[p].kv[k][0])) snprintf(vals[i], 24, "%s", pre[p].kv[k][1]);
    };
    if(!inited) { for(int p = 0; p < npre; p++) if(!strcmp(pre[p].name, "standard")) presetIdx = p; apply_preset(presetIdx); inited = 1; }
    ImGui::TextWrapped("Makes a randomized game from your ROM and the mods that are switched on (other randomizer seeds "
                       "aside). The result is added to your mods with a spoiler log, and you play it from a new game.");
    ImGui::Spacing();
    ImGui::BeginDisabled(st->randoBusy);
    ImGui::SetNextItemWidth(baseFont * 10);
    if(ImGui::BeginCombo("Preset", pre[presetIdx].name)) {
      for(int p = 0; p < npre; p++) if(ImGui::Selectable(pre[p].name, p == presetIdx)) { presetIdx = p; apply_preset(p); }
      ImGui::EndCombo();
    }
    help_marker("light: small changes. standard: classes, skills, growths and children's parents shuffled. chaos: everything, enemies too.");
    ImGui::SetNextItemWidth(baseFont * 10);
    ImGui::InputTextWithHint("Seed", "random", seedText, sizeof seedText, ImGuiInputTextFlags_CharsDecimal);
    help_marker("The same seed and options always make the same game. Leave it empty for a new random seed.");
    ImGui::Spacing();
    if(ImGui::Button("Randomize")) {
      long long seed = atoll(seedText);
      if(seed <= 0) { srand((unsigned)time(NULL) ^ SDL_GetTicks()); seed = 1 + ((long long)rand() * 32768 + rand()) % 999999999; }
      snprintf(st->randoPreset, sizeof st->randoPreset, "%s", pre[presetIdx].name);
      st->randoSeed = seed; st->randoN = 0;
      for(int i = 0; i < n && i < 64; i++) { st->randoKeys[st->randoN] = opts[i].key; st->randoVals[st->randoN] = vals[i]; st->randoN++; }
      act |= MA_RANDOMIZE;
    }
    ImGui::EndDisabled();
    if(st->randoBusy) { ImGui::SameLine(); ImGui::Text("Randomizing%.*s (about half a minute)", (int)(SDL_GetTicks() / 400 % 4), "..."); }
    if(st->randoMsg[0]) ImGui::TextWrapped("%s", st->randoMsg);
    if(st->randoDone && !st->testPlay) restart_button(st, &act);
    ImGui::Spacing();
    ImGui::BeginDisabled(st->randoBusy);
    if(ImGui::CollapsingHeader("Options")) {
      for(int i = 0; i < n; i++) {
        KitOption* o = &opts[i];
        ImGui::PushID(i);
        ImGui::SetNextItemWidth(baseFont * 10);
        if(o->isInt) {
          int v = atoi(vals[i]);
          if(ImGui::SliderInt(o->label, &v, o->lo, o->hi)) snprintf(vals[i], 24, "%d", v);
        } else if(ImGui::BeginCombo(o->label, vals[i])) {
          for(int c = 0; c < o->nchoices; c++) if(ImGui::Selectable(o->choices[c], !strcmp(vals[i], o->choices[c]))) snprintf(vals[i], 24, "%s", o->choices[c]);
          ImGui::EndCombo();
        }
        if(o->help[0]) help_marker(o->help);
        ImGui::PopID();
      }
    }
    ImGui::EndDisabled();
  }
  ImGui::End();
  return act;
}

extern "C" int menu_frame(MenuState* st) {
  int act = 0;
  ImGui_ImplSDLRenderer2_NewFrame();
  ImGui_ImplSDL2_NewFrame();
  // scale the UI with the window: 18px text at 720 lines, never smaller than 16px
  int ww, wh; SDL_GetRendererOutputSize(gRen, &ww, &wh);
  float px = wh / 40.0f; if(px < 16) px = 16; if(px > 36) px = 36;
  baseFont = px;
  ImGui::GetIO().FontGlobalScale = px / 36.0f;
  ImGui::NewFrame();

  if(visible && ImGui::BeginMainMenuBar()) {
    bool gameOpen = ImGui::BeginMenu("Game");
    if(focusBar && !gameOpen) { // arrows / d-pad work right away: "Game" is selected
      ImGuiWindow* w = ImGui::GetCurrentWindow();
      ImGui::FocusWindow(w); ImGui::SetFocusID(ImGui::GetItemID(), w); GImGui->NavCursorVisible = true;
      GImGui->NavInitRequest = false; GImGui->NavInitResult.ID = 0; // keep "Game", not the first item submitted after it
      focusBar = false;
    }
    if(gameOpen) {
      if(ImGui::MenuItem("Save state", "F5")) act |= MA_SAVE_STATE;
      if(ImGui::MenuItem("Load state", "F7", false, st->slotUsed[*st->slot] != 0)) act |= MA_LOAD_STATE;
      if(ImGui::BeginMenu("State slot")) {
        for(int i = 1; i <= 9; i++) {
          char l[64]; snprintf(l, sizeof l, "Slot %d", i);
          if(ImGui::MenuItem(l, st->slotUsed[i] ? st->slotTime[i] : "empty", *st->slot == i)) { *st->slot = i; act |= MA_SAVE_CONFIG; }
        }
        ImGui::EndMenu();
      }
      ImGui::Separator();
      { bool p = *st->paused != 0; if(ImGui::MenuItem("Pause", "P", &p)) *st->paused = p; }
      if(ImGui::MenuItem("Reset game")) act |= MA_RESET;
      help_marker("Like pressing the console's reset button. Unsaved progress since your last in-game save is lost.");
      ImGui::Separator();
      if(ImGui::MenuItem("Quit", "Alt+F4")) act |= MA_QUIT;
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Graphics")) {
      if(check("Widescreen (16:9)", st->widescreen, "F4")) act |= MA_VIDEO | MA_SAVE_CONFIG;
      help_marker("Shows more of the map and battle backgrounds, using only what the game itself has. Menus and story scenes stay 4:3.");
      ImGui::SeparatorText("Pixel shape");
      if(ImGui::MenuItem("Square pixels (8:7)", NULL, !*st->aspect43)) { *st->aspect43 = 0; act |= MA_VIDEO | MA_SAVE_CONFIG; }
      if(ImGui::MenuItem("TV shape (4:3)", "F2", *st->aspect43 != 0)) { *st->aspect43 = 1; act |= MA_VIDEO | MA_SAVE_CONFIG; }
      ImGui::SeparatorText("Window");
      if(check("Fullscreen", st->fullscreen, "F11")) act |= MA_VIDEO | MA_SAVE_CONFIG;
      if(ImGui::BeginMenu("Window size", !*st->fullscreen)) {
        for(int s = 1; s <= 6; s++) { char l[16]; snprintf(l, sizeof l, "%dx", s); if(ImGui::MenuItem(l, NULL, *st->scale == s)) { *st->scale = s; act |= MA_VIDEO | MA_SAVE_CONFIG; } }
        ImGui::EndMenu();
      }
      if(check("Smooth scaling", st->smooth)) act |= MA_VIDEO | MA_SAVE_CONFIG;
      if(check("VSync", st->vsync)) act |= MA_VIDEO | MA_SAVE_CONFIG;
      if(check("Show FPS", st->showFps)) act |= MA_SAVE_CONFIG;
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Audio")) {
      ImGui::SetNextItemWidth(baseFont * 10);
      if(ImGui::SliderInt("Volume", st->volume, 0, 100, "%d%%")) act |= MA_SAVE_CONFIG;
      if(check("Mute", st->mute)) act |= MA_SAVE_CONFIG;
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Enhancements")) {
      ImGui::SeparatorText("Map");
      if(!st->hoverActive) ImGui::BeginDisabled();
      if(check("Unit stats in hover box", st->hoverstats)) { act |= MA_SAVE_CONFIG; menu_notify(*st->hoverstats ? "Unit stats on" : "Unit stats off"); }
      if(!st->hoverActive) ImGui::EndDisabled();
      help_marker(st->hoverActive
        ? "Adds MT (attack), HIT, AS (attack speed) and AVO (avoid) to the box shown when the cursor is on a unit, using the game's own status-screen numbers. Changes show the next time the box is drawn."
        : "Not available for this ROM: its code is different where the box is drawn.");
      ImGui::SeparatorText("Speed");
      { bool f = *st->ffToggle != 0; if(ImGui::MenuItem("Fast-forward", "F3 / hold Tab", &f)) *st->ffToggle = f; }
      ImGui::SetNextItemWidth(baseFont * 10);
      if(ImGui::SliderInt("Fast-forward speed", st->turbo, 2, 8, "%dx")) act |= MA_SAVE_CONFIG;
      help_marker("The game runs faster while the music keeps its normal tempo.");
      ImGui::SeparatorText("Automatic speed-ups");
      struct { const char* label; int* v; const char* help; } su[4] = {
        { "Faster text", st->ffText, "Speeds the game up while text is being written out (story scenes, conversations, village visits, battle quotes). It goes back to normal speed when the text waits for your button press." },
        { "Faster battles", st->ffBattle, "Speeds up the battle scenes (the animated fights)." },
        { "Faster enemy phase", st->ffEnemy, "Speeds the game up while the other armies (enemies and allies) take their turns." },
        { "Faster cursor", st->ffCursor, "Speeds the game up while you hold a direction on the map in your phase, so the cursor and the map scroll faster." },
      };
      for(int i = 0; i < 4; i++) {
        ImGui::SetNextItemWidth(baseFont * 10);
        if(ImGui::SliderInt(su[i].label, su[i].v, 1, 8, *su[i].v <= 1 ? "Off" : "%dx")) act |= MA_SAVE_CONFIG;
        help_marker(su[i].help);
      }
      ImGui::TextDisabled("Music always plays at its normal speed.");
      ImGui::SeparatorText("Menu");
      if(check("Pause the game while this menu is open", st->pauseInMenu)) act |= MA_SAVE_CONFIG;
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Controls")) {
      ImGui::TextDisabled("Click a box, then press the key or gamepad button you want");
      if(ImGui::BeginTable("keys", 3, ImGuiTableFlags_SizingFixedFit | ImGuiTableFlags_RowBg)) {
        ImGui::TableSetupColumn("SNES"); ImGui::TableSetupColumn("Keyboard"); ImGui::TableSetupColumn("Gamepad");
        ImGui::TableHeadersRow();
        static const int order[13] = { 8, 0, 9, 1, 10, 11, 3, 2, PAD_FF, 4, 5, 6, 7 }; // A B X Y L R Start Select FF Up Down Left Right
        for(int oi = 0; oi < 13; oi++) {
          int i = order[oi];
          ImGui::PushID(oi);
          ImGui::TableNextRow();
          ImGui::TableNextColumn(); ImGui::AlignTextToFramePadding(); ImGui::Text("%s", i == PAD_FF ? "Fast-forward" : BTN_LABELS[i]);
          ImGui::TableNextColumn();
          char l[96];
          if(i == PAD_FF) { ImGui::TextDisabled("Tab (hold) / F3"); }
          else {
            if(bindingFor == i) snprintf(l, sizeof l, "press a key...##k");
            else snprintf(l, sizeof l, "%s##k", st->keys[i] == SDLK_UNKNOWN ? "(none)" : SDL_GetKeyName(st->keys[i]));
            if(ImGui::Button(l, ImVec2(baseFont * 8, 0))) { bindingFor = i; padBindingFor = -1; }
          }
          ImGui::TableNextColumn();
          if(i >= 4 && i <= 7) ImGui::TextDisabled("D-pad / left stick");
          else {
            if(padBindingFor == i) snprintf(l, sizeof l, "press a button...##p");
            else snprintf(l, sizeof l, "%s##p", pad_input_label(st->pad[i]));
            if(ImGui::Button(l, ImVec2(baseFont * 14, 0))) {
              padBindingFor = i; bindingFor = -1;
              ImGui::GetIO().ConfigFlags &= ~ImGuiConfigFlags_NavEnableGamepad; // the next button press is the binding
            }
          }
          ImGui::PopID();
        }
        ImGui::EndTable();
      }
      if(!st->padCount) ImGui::TextDisabled("No gamepad connected.");
      if(ImGui::Button("Default keys")) act |= MA_KEYS_DEFAULT | MA_SAVE_CONFIG;
      ImGui::SameLine();
      if(ImGui::Button("Default gamepad buttons")) act |= MA_PAD_DEFAULT | MA_SAVE_CONFIG;
      ImGui::SameLine();
      if(ImGui::Button("All shortcuts...")) showControls = true;
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Cheats")) {
      if(!st->armyCount) ImGui::TextDisabled("Cheats work on your army during a chapter.");
      else {
        ImGui::BeginDisabled(!st->selOk);
        if(st->selOk) ImGui::SeparatorText(st->sel.name);
        else ImGui::SeparatorText("Unit under the cursor");
        if(st->selOk) ImGui::TextDisabled("HP %d/%d   Level %d   EXP %d   Gold %d", st->sel.hp, st->sel.maxHp, st->sel.level, st->sel.exp, st->sel.gold);
        else ImGui::TextDisabled("Put the cursor on one of your units first.");
        if(ImGui::MenuItem("Restore HP")) { st->cheatWhat = CHEAT_HEAL; st->cheatAll = 0; act |= MA_CHEAT; }
        if(ImGui::MenuItem("Gold 50,000")) { st->cheatWhat = CHEAT_GOLD; st->cheatAll = 0; act |= MA_CHEAT; }
        if(ImGui::MenuItem("EXP 99 (levels up after the next fight)")) { st->cheatWhat = CHEAT_EXP; st->cheatAll = 0; act |= MA_CHEAT; }
        ImGui::EndDisabled();
        char t[64]; snprintf(t, sizeof t, "Your whole army (%d units)", st->armyCount);
        ImGui::SeparatorText(t);
        if(ImGui::MenuItem("Restore everyone's HP", NULL, false, st->armyHurt > 0)) { st->cheatWhat = CHEAT_HEAL; st->cheatAll = 1; act |= MA_CHEAT; }
        if(ImGui::MenuItem("Gold 50,000 for everyone")) { st->cheatWhat = CHEAT_GOLD; st->cheatAll = 1; act |= MA_CHEAT; }
        if(ImGui::MenuItem("EXP 99 for everyone")) { st->cheatWhat = CHEAT_EXP; st->cheatAll = 1; act |= MA_CHEAT; }
        ImGui::Spacing();
        ImGui::TextDisabled("Cheats change your game for good: make a save state first if you're unsure.");
      }
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Mods")) {
      if(ImGui::MenuItem("Mods...")) { mods_rescan(); showMods = true; }
      if(ImGui::MenuItem("Randomizer...")) showRando = true;
      ImGui::Separator();
      if(ImGui::MenuItem("Open the mods folder")) open_path(mods_dir());
      ImGui::EndMenu();
    }
    if(ImGui::BeginMenu("Help")) {
      if(ImGui::MenuItem("Controls and shortcuts...")) showControls = true;
      if(ImGui::MenuItem("About...")) showAbout = true;
      ImGui::EndMenu();
    }
    // right side: status
    char status[96];
    if(*st->paused || *st->pauseInMenu) snprintf(status, sizeof status, "Game paused   F1 / Esc closes this menu");
    else snprintf(status, sizeof status, "%.0f fps   F1 / Esc closes this menu", st->fps);
    float w = ImGui::CalcTextSize(status).x;
    ImGui::SameLine(ImGui::GetWindowWidth() - w - baseFont);
    ImGui::TextDisabled("%s", status);
    ImGui::EndMainMenuBar();
  }

  if(showControls) {
    ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
    if(ImGui::Begin("Controls and shortcuts", &showControls, ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_AlwaysAutoResize)) {
      if(ImGui::BeginTable("c", 2, ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingFixedFit)) {
        static const char* rows[][2] = {
          { "F1 / Esc / right stick click", "open or close this menu" },
          { "F5 / F7", "save / load state" }, { "F6 / F8", "previous / next state slot" },
          { "Tab (hold), right trigger", "fast-forward" }, { "F3", "fast-forward on/off" },
          { "F4", "widescreen on/off" }, { "F2", "square pixels / TV shape" },
          { "F11, Alt+Enter", "fullscreen" }, { "P", "pause" },
          { "Gamepad buttons", "by default by position, as on a SNES pad:" }, { "", "right = A, bottom = B, top = X, left = Y" }, { "", "(change them under Controls)" },
        };
        for(auto& r : rows) { ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextUnformatted(r[0]); ImGui::TableNextColumn(); ImGui::TextUnformatted(r[1]); }
        ImGui::EndTable();
      }
    }
    ImGui::End();
  }
  if(bindPadSaved) { bindPadSaved = 0; act |= MA_SAVE_CONFIG; }
  if(showMods) act |= mods_window(st);
  if(showRando) act |= rando_window(st);
  if(showAbout) {
    ImGui::SetNextWindowSize(ImVec2(baseFont * 26, 0), ImGuiCond_Appearing);
    ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
    if(ImGui::Begin("About", &showAbout, ImGuiWindowFlags_NoCollapse)) {
      ImGui::Text("Fire Emblem: Genealogy of the Holy War - PC port %s", st->version);
      ImGui::Separator();
      ImGui::TextWrapped("ROM: %s", st->romName);
      ImGui::TextWrapped("%s", st->romInfo);
      ImGui::Spacing();
      if(st->recompiled) ImGui::TextWrapped("Running the game's code translated to C: %llu blocks run, %llu instructions interpreted (code not translated yet; it is learned for next launch).", st->compiledBlocks, st->interpOps);
      else ImGui::TextWrapped("Running the game in the interpreter.");
      ImGui::Spacing();
      ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyle().Colors[ImGuiCol_TextDisabled]);
      ImGui::TextWrapped("Uses LakeSnes (MIT), SDL2 (zlib), TinyCC (LGPL), Dear ImGui (MIT) and the Roboto font (Apache 2.0). Licenses are in the licenses folder.");
      ImGui::TextWrapped("Fire Emblem is (c) Nintendo / Intelligent Systems. This program contains no game data; it runs from your own ROM.");
      ImGui::PopStyleColor();
    }
    ImGui::End();
  }

  // FPS overlay (top right) when the menu is closed
  if(*st->showFps && !visible) {
    ImGui::SetNextWindowPos(ImVec2(ImGui::GetIO().DisplaySize.x - baseFont * 0.6f, baseFont * 0.6f), ImGuiCond_Always, ImVec2(1, 0));
    ImGui::SetNextWindowBgAlpha(0.55f);
    ImGui::Begin("fps", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoFocusOnAppearing);
    if(st->speed > 1) ImGui::Text("%.0f fps  x%d", st->fps, st->speed); else ImGui::Text("%.0f fps", st->fps);
    ImGui::End();
  }
  else if(st->speed > 1 && !visible) { // speed indicator while fast-forwarding (by hand or automatically)
    ImGui::SetNextWindowPos(ImVec2(ImGui::GetIO().DisplaySize.x - baseFont * 0.6f, baseFont * 0.6f), ImGuiCond_Always, ImVec2(1, 0));
    ImGui::SetNextWindowBgAlpha(0.45f);
    ImGui::Begin("speed", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoFocusOnAppearing);
    ImGui::Text("\xC2\xBB %dx", st->speed);
    ImGui::End();
  }
  // toast
  if(toast[0] && SDL_GetTicks() < toastUntil) {
    ImGui::SetNextWindowPos(ImVec2(baseFont * 0.8f, ImGui::GetIO().DisplaySize.y - baseFont * 0.8f), ImGuiCond_Always, ImVec2(0, 1));
    ImGui::SetNextWindowBgAlpha(0.75f);
    ImGui::Begin("toast", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoFocusOnAppearing);
    ImGui::TextUnformatted(toast);
    ImGui::End();
  }
  ImGui::Render();
  return act;
}

extern "C" void menu_render(void) {
  ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData(), gRen);
}
