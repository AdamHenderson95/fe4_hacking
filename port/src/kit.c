// fe4kit from inside the port: find the kit, read its randomizer options, run the randomizer.
// The kit is BuilderOfTheHolyWar.exe (FE4KitEditor.exe up to kit v15) on Windows, or the kit's Python scripts (fe4rando.py + python3), found next
// to the port or in a "fe4kit" folder beside it. It runs as a separate process in the background.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#endif
#include "kit.h"

static char kitExe[1100];     // BuilderOfTheHolyWar.exe / FE4KitEditor.exe, or fe4rando.py
static int kitIsPy;
static char cache[1100];
static char err[512];
static char logPath[1200], logText[8192];
static KitOption opts[KIT_MAXOPT]; static int nopts = -1; // -1 not loaded
static KitPreset presets[8]; static int npre;
static int loadingOptions;

static int exists(const char* p) { struct stat st; return stat(p, &st) == 0; }
static long long mtime(const char* p) { struct stat st; return stat(p, &st) == 0 ? (long long)st.st_mtime : 0; }

int kit_init(const char* base, const char* cacheDir) {
  snprintf(cache, sizeof cache, "%s", cacheDir);
  const char* exes[] = { "BuilderOfTheHolyWar.exe", "fe4kit/BuilderOfTheHolyWar.exe", "tools/BuilderOfTheHolyWar.exe",
                         "FE4KitEditor.exe", "fe4kit/FE4KitEditor.exe", "tools/FE4KitEditor.exe" };
  const char* pys[] = { "fe4kit/fe4rando.py", "fe4rando.py" };
  kitExe[0] = 0;
#ifdef _WIN32
  for(int i = 0; i < 6 && !kitExe[0]; i++) { char p[1100]; snprintf(p, sizeof p, "%s%s", base, exes[i]); if(exists(p)) { snprintf(kitExe, sizeof kitExe, "%s", p); kitIsPy = 0; } }
#else
  (void)exes;
#endif
  for(int i = 0; i < 2 && !kitExe[0]; i++) { char p[1100]; snprintf(p, sizeof p, "%s%s", base, pys[i]); if(exists(p)) { snprintf(kitExe, sizeof kitExe, "%s", p); kitIsPy = 1; } }
  if(kitExe[0]) printf("fe4kit: %s\n", kitExe);
  return kitExe[0] != 0;
}
int kit_found(void) { return kitExe[0] != 0; }
const char* kit_where(void) { return kitExe; }
const char* kit_error(void) { return err; }
const char* kit_rando_log(void) { return logText; }

// ---------------- background process ----------------
#ifdef _WIN32
static HANDLE proc;
#else
static pid_t proc;
#endif
static int running;

static void quote(char* out, int n, const char* s) { // Windows command-line quoting (no embedded quotes in our args)
  snprintf(out, n, "\"%s\"", s);
}

static int start(const char* const* args, int nargs) {
  if(running) { snprintf(err, sizeof err, "the kit is still busy"); return 0; }
  snprintf(logPath, sizeof logPath, "%skit_log.txt", cache);
  remove(logPath);
  logText[0] = 0;
#ifdef _WIN32
  char cmd[8192]; int k = 0; char q[1300];
  if(kitIsPy) { k += snprintf(cmd + k, sizeof cmd - k, "pythonw "); }
  quote(q, sizeof q, kitExe); k += snprintf(cmd + k, sizeof cmd - k, "%s", q);
  if(!kitIsPy) k += snprintf(cmd + k, sizeof cmd - k, " rando");
  for(int i = 0; i < nargs; i++) { quote(q, sizeof q, args[i]); k += snprintf(cmd + k, sizeof cmd - k, " %s", q); }
  quote(q, sizeof q, logPath); k += snprintf(cmd + k, sizeof cmd - k, " --log %s", q);
  STARTUPINFOA si; memset(&si, 0, sizeof si); si.cb = sizeof si;
  PROCESS_INFORMATION pi;
  if(!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
    snprintf(err, sizeof err, "couldn't start the kit (%s)", kitExe); return 0;
  }
  CloseHandle(pi.hThread); proc = pi.hProcess;
#else
  const char* av[80]; int a = 0;
  if(kitIsPy) av[a++] = "python3";
  av[a++] = kitExe;
  if(!kitIsPy) av[a++] = "rando";
  for(int i = 0; i < nargs && a < 76; i++) av[a++] = args[i];
  av[a++] = "--log"; av[a++] = logPath; av[a] = NULL;
  pid_t p = fork();
  if(p < 0) { snprintf(err, sizeof err, "couldn't start the kit"); return 0; }
  if(p == 0) { execvp(av[0], (char* const*)av); _exit(127); }
  proc = p;
#endif
  running = 1;
  return 1;
}

static void read_log(void) {
  FILE* f = fopen(logPath, "rb");
  logText[0] = 0;
  if(f) { size_t n = fread(logText, 1, sizeof logText - 1, f); logText[n] = 0; fclose(f); }
}

// 1 running, 0 idle, 2 done ok, -1 failed
static int poll_proc(void) {
  if(!running) return 0;
  int code;
#ifdef _WIN32
  if(WaitForSingleObject(proc, 0) == WAIT_TIMEOUT) return 1;
  DWORD c = 1; GetExitCodeProcess(proc, &c); CloseHandle(proc); code = (int)c;
#else
  int st; pid_t r = waitpid(proc, &st, WNOHANG);
  if(r == 0) return 1;
  code = (r == proc && WIFEXITED(st)) ? WEXITSTATUS(st) : 1;
#endif
  running = 0;
  read_log();
  return code == 0 ? 2 : -1;
}

// ---------------- options ----------------
static void parse_tsv(const char* path) {
  FILE* f = fopen(path, "r"); if(!f) return;
  char line[1200]; nopts = 0; npre = 0;
  while(fgets(line, sizeof line, f)) {
    line[strcspn(line, "\r\n")] = 0;
    char* col[8]; int nc = 0; char* s = line;
    while(nc < 8) { col[nc++] = s; char* t = strchr(s, '\t'); if(!t) break; *t = 0; s = t + 1; }
    if(!strcmp(col[0], "O") && nc >= 7 && nopts < KIT_MAXOPT) {
      KitOption* o = &opts[nopts++]; memset(o, 0, sizeof *o);
      snprintf(o->key, sizeof o->key, "%s", col[1]); snprintf(o->def, sizeof o->def, "%s", col[2]);
      o->isInt = !strcmp(col[3], "int");
      if(o->isInt) { sscanf(col[4], "%d,%d", &o->lo, &o->hi); }
      else { char* c = col[4]; while(c && *c && o->nchoices < 8) { char* e = strchr(c, ','); if(e) *e = 0; snprintf(o->choices[o->nchoices++], 24, "%s", c); c = e ? e + 1 : NULL; } }
      snprintf(o->label, sizeof o->label, "%s", col[5]); snprintf(o->help, sizeof o->help, "%s", col[6]);
    } else if(!strcmp(col[0], "P") && nc >= 2 && npre < 8) {
      KitPreset* p = &presets[npre++]; memset(p, 0, sizeof *p);
      snprintf(p->name, sizeof p->name, "%s", col[1]);
      char* c = nc >= 3 ? col[2] : NULL;
      while(c && *c && p->n < KIT_MAXOPT) {
        char* e = strchr(c, ';'); if(e) *e = 0;
        char* eq = strchr(c, '=');
        if(eq) { *eq = 0; snprintf(p->kv[p->n][0], 24, "%s", c); snprintf(p->kv[p->n][1], 24, "%s", eq + 1); p->n++; }
        c = e ? e + 1 : NULL;
      }
    }
  }
  fclose(f);
  if(nopts == 0) nopts = -1;
}

int kit_options(KitOption** o, KitPreset** p, int* np) {
  *o = opts; *p = presets; *np = npre;
  if(nopts > 0) return nopts;
  if(!kitExe[0]) { snprintf(err, sizeof err, "fe4kit wasn't found next to the port"); return 0; }
  char tsv[1200]; snprintf(tsv, sizeof tsv, "%skit_options.tsv", cache);
  if(loadingOptions) {
    int r = poll_proc();
    if(r == 1) return -1;
    loadingOptions = 0;
    if(r == 2) parse_tsv(tsv);
    if(nopts <= 0) { snprintf(err, sizeof err, "the kit couldn't list its options: %.400s", logText); nopts = 0; return 0; }
    *np = npre; return nopts;
  }
  if(nopts == 0) return 0; // tried and failed
  if(exists(tsv) && mtime(tsv) >= mtime(kitExe)) { parse_tsv(tsv); if(nopts > 0) { *np = npre; return nopts; } }
  const char* args[] = { "--list-tsv", tsv };
  if(!start(args, 2)) { nopts = 0; return 0; }
  loadingOptions = 1;
  return -1;
}

int kit_rando_start(const char* inRom, const char* outIps, const char* outSpoiler, long long seed,
                    const char* preset, const char* const* keys, const char* const* vals, int n) {
  (void)outSpoiler;
  static char seedS[32], outRom[1200], kv[KIT_MAXOPT][64];
  snprintf(seedS, sizeof seedS, "%lld", seed);
  snprintf(outRom, sizeof outRom, "%srando_out.smc", cache);
  const char* args[16 + 2 * KIT_MAXOPT]; int a = 0;
  args[a++] = inRom; args[a++] = outRom;
  args[a++] = "--seed"; args[a++] = seedS;
  args[a++] = "--preset"; args[a++] = preset;
  args[a++] = "--ips"; args[a++] = outIps;
  for(int i = 0; i < n && i < KIT_MAXOPT; i++) { snprintf(kv[i], sizeof kv[i], "%s=%s", keys[i], vals[i]); args[a++] = "--opt"; args[a++] = kv[i]; }
  err[0] = 0;
  return start(args, a);
}

int kit_rando_poll(void) {
  if(loadingOptions) return 0;
  int r = poll_proc();
  if(r == -1) {
    const char* last = logText; // last non-empty line of the log says what went wrong
    for(const char* p = logText; *p; p++) if(*p == '\n' && p[1] && p[1] != '\n') last = p + 1;
    snprintf(err, sizeof err, "the randomizer stopped: %.400s", last);
  }
  return r;
}
