// shared movie loader: lines "<frame> <buttons>", buttons from "BYsSUDLRAXlr" or '-'
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static const char* MV_BTN = "BYsSUDLRAXlr";
typedef struct { int frame; uint16_t mask; } MovieEv;
static MovieEv mv_ev[200000]; static int mv_n;
static void movie_load(const char* path) {
  FILE* f = fopen(path, "r"); if(!f) return;
  char line[256];
  while(fgets(line, sizeof line, f)) {
    if(line[0] == '#' || line[0] == '\n') continue;
    int fr; char b[64] = "-";
    if(sscanf(line, "%d %63s", &fr, b) >= 1) {
      uint16_t m = 0;
      for(char* s = b; *s; s++) { const char* p = strchr(MV_BTN, *s); if(p && *s != '-') m |= 1 << (p - MV_BTN); }
      mv_ev[mv_n].frame = fr; mv_ev[mv_n].mask = m; mv_n++;
    }
  }
  fclose(f);
}
static uint16_t movie_mask(int frame) {
  // binary search last event with frame <= frame
  int lo = 0, hi = mv_n - 1, r = -1;
  while(lo <= hi) { int mid = (lo + hi) / 2; if(mv_ev[mid].frame <= frame) { r = mid; lo = mid + 1; } else hi = mid - 1; }
  return r < 0 ? 0 : mv_ev[r].mask;
}
