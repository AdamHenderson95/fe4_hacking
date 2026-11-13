// Custom music: an MSU-1 audio chip for the port (see music.h).
//
// Tracks are files in the music folder named after the song number the game asks for:
//   17.ogg, 017 Prologue.flac, 17 - anything.mp3, 17.wav, or MSU-1 packs' name-17.pcm.
// Loop points: MSU-1 .pcm headers, the LOOPSTART / LOOPLENGTH / LOOPEND tags of .ogg files (in samples),
// or a text file with the same name and .txt (loop_start = 12.5 for seconds, loop_start_sample = 551250
// for samples; loop_end / loop_end_sample likewise). Without one, a track loops from its start.
//
// The chip: $2000 status (bit 6 audio busy, 5 repeating, 4 playing, 3 track missing, revision 2),
// $2002-$2007 "S-MSU1"; writes $2004/$2005 choose a track (loads it on $2005), $2006 volume,
// $2007 control (bit 0 play, 1 repeat, 2 resume). Data reads ($2001) give 0.
#include "music.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#endif

#define STB_VORBIS_NO_PUSHDATA_API
#include "../third_party/audio/stb_vorbis.c"
#undef L
#undef C
#undef R
#define DR_FLAC_IMPLEMENTATION
#define DR_FLAC_NO_OGG
#include "../third_party/audio/dr_flac.h"
#define DR_MP3_IMPLEMENTATION
#include "../third_party/audio/dr_mp3.h"
#define DR_WAV_IMPLEMENTATION
#include "../third_party/audio/dr_wav.h"

#define MAXT 1000
static char dir[1024];
static char* files[MAXT];
static int nfiles, enabled = 1;

enum { T_NONE, T_OGG, T_FLAC, T_MP3, T_WAV, T_PCM };
typedef struct {
  int type; void* h; FILE* f;
  int rate, ch;
  uint64_t len, loopStart, loopEnd, pos;   // in source frames; loopEnd 0 = the end
} Src;

static Src src;                 // the track playing
static int track, reqTrack, lastReq, missing, playing, repeat;
static int vol = 255;           // $2006
static float curVol = 1.0f;     // smoothed
static double frac;             // resampling position between source frames
static int16_t cur[2], nxt[2];  // the two source frames around the output position
static int prevTrack; static uint64_t prevPos;   // the track before this one, for going back to it

// ---------------------------------------------------------------- files
static int ext_ok(const char* n) {
  const char* e = strrchr(n, '.'); if(!e) return 0;
  char x[8] = { 0 }; for(int i = 0; i < 7 && e[i + 1]; i++) x[i] = (char)tolower((unsigned char)e[i + 1]);
  return !strcmp(x, "ogg") || !strcmp(x, "flac") || !strcmp(x, "mp3") || !strcmp(x, "wav") || !strcmp(x, "pcm");
}
static int number_of(const char* n) {
  if(isdigit((unsigned char)n[0])) return atoi(n);           // 17.ogg, 017 Name.flac
  const char* e = strrchr(n, '.'); const char* d = e;           // name-17.pcm
  while(d > n && isdigit((unsigned char)d[-1])) d--;
  if(d < e && d > n && d[-1] == '-') return atoi(d);
  return -1;
}
static void add_file(const char* n) {
  if(!ext_ok(n)) return;
  int t = number_of(n);
  if(t < 1 || t >= MAXT) return;
  if(files[t]) {                                                // two files for one song: keep the first by name
    if(strcmp(n, files[t]) >= 0) return;
    free(files[t]); nfiles--;
  }
  files[t] = malloc(strlen(n) + 1); strcpy(files[t], n); nfiles++;
}
void music_rescan(void) {
  for(int i = 0; i < MAXT; i++) { free(files[i]); files[i] = NULL; }
  nfiles = 0;
#ifdef _WIN32
  char pat[1100]; snprintf(pat, sizeof pat, "%s*", dir);
  WIN32_FIND_DATAA fd; HANDLE h = FindFirstFileA(pat, &fd);
  if(h != INVALID_HANDLE_VALUE) { do { if(!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) add_file(fd.cFileName); } while(FindNextFileA(h, &fd)); FindClose(h); }
#else
  DIR* d = opendir(dir);
  if(d) { struct dirent* e; while((e = readdir(d))) if(e->d_name[0] != '.') add_file(e->d_name); closedir(d); }
#endif
}
void music_init(const char* d) { snprintf(dir, sizeof dir, "%s", d); music_rescan(); }
const char* music_dir(void) { return dir; }
int music_count(void) { return nfiles; }
const char* music_file(int t) { return t > 0 && t < MAXT ? files[t] : NULL; }
void music_set_enabled(int on) { enabled = on; if(!on) music_stop(); }
int music_enabled(void) { return enabled; }
int music_playing(void) { return playing ? track : 0; }
int music_last_request(void) { return lastReq; }
void music_note_request(int s) { lastReq = s; }

// ---------------------------------------------------------------- decoding
static void src_close(Src* s) {
  switch(s->type) {
    case T_OGG: stb_vorbis_close(s->h); break;
    case T_FLAC: drflac_close(s->h); break;
    case T_MP3: drmp3_uninit(s->h); free(s->h); break;
    case T_WAV: drwav_uninit(s->h); free(s->h); break;
    case T_PCM: fclose(s->f); break;
  }
  memset(s, 0, sizeof *s);
}
static int prefix_ci(const char* s, const char* p) {
  for(; *p; s++, p++) if(tolower((unsigned char)*s) != tolower((unsigned char)*p)) return 0;
  return 1;
}
static double parse_num(const char* v, int* isSec) { *isSec = strchr(v, '.') != NULL; return atof(v); }
static void read_sidecar(Src* s, const char* path) {
  char p[1200]; snprintf(p, sizeof p, "%s", path);
  char* e = strrchr(p, '.'); if(e) strcpy(e, ".txt"); else return;
  FILE* f = fopen(p, "r"); if(!f) return;
  char line[256];
  while(fgets(line, sizeof line, f)) {
    char* eq = strchr(line, '='); if(!eq) continue;
    *eq = 0; char* k = line; char* v = eq + 1;
    while(*k == ' ' || *k == '\t') k++;
    for(char* q = k + strlen(k); q > k && (q[-1] == ' ' || q[-1] == '\t'); ) *--q = 0;
    int sec; double x = parse_num(v, &sec);
    if(!strcmp(k, "loop_start")) s->loopStart = (uint64_t)(x * s->rate);
    else if(!strcmp(k, "loop_end")) s->loopEnd = (uint64_t)(x * s->rate);
    else if(!strcmp(k, "loop_start_sample")) s->loopStart = (uint64_t)x;
    else if(!strcmp(k, "loop_end_sample")) s->loopEnd = (uint64_t)x;
  }
  fclose(f);
}
static int src_open_path(Src* s, const char* path, const char* name);
static int src_open(Src* s, const char* name) {
  char path[1200]; snprintf(path, sizeof path, "%s%s", dir, name);
  return src_open_path(s, path, name);
}
static int src_open_path(Src* s, const char* path, const char* name) {
  memset(s, 0, sizeof *s);
  const char* e = strrchr(name, '.'); char x[8] = { 0 };
  for(int i = 0; i < 7 && e && e[i + 1]; i++) x[i] = (char)tolower((unsigned char)e[i + 1]);
  if(!strcmp(x, "ogg")) {
    int err; stb_vorbis* v = stb_vorbis_open_filename(path, &err, NULL); if(!v) return 0;
    stb_vorbis_info in = stb_vorbis_get_info(v);
    s->type = T_OGG; s->h = v; s->rate = in.sample_rate; s->ch = in.channels; s->len = stb_vorbis_stream_length_in_samples(v);
    stb_vorbis_comment c = stb_vorbis_get_comment(v);
    uint64_t ls = 0, ll = 0, le = 0;
    for(int i = 0; i < c.comment_list_length; i++) {
      const char* t = c.comment_list[i];
      if(prefix_ci(t, "LOOPSTART=")) ls = strtoull(t + 10, NULL, 10);
      else if(prefix_ci(t, "LOOPLENGTH=")) ll = strtoull(t + 11, NULL, 10);
      else if(prefix_ci(t, "LOOPEND=")) le = strtoull(t + 8, NULL, 10);
    }
    s->loopStart = ls; s->loopEnd = le ? le : ll ? ls + ll : 0;
  } else if(!strcmp(x, "flac")) {
    drflac* fl = drflac_open_file(path, NULL); if(!fl) return 0;
    s->type = T_FLAC; s->h = fl; s->rate = fl->sampleRate; s->ch = fl->channels; s->len = fl->totalPCMFrameCount;
  } else if(!strcmp(x, "mp3")) {
    drmp3* m = malloc(sizeof *m); if(!drmp3_init_file(m, path, NULL)) { free(m); return 0; }
    s->type = T_MP3; s->h = m; s->rate = m->sampleRate; s->ch = m->channels; s->len = drmp3_get_pcm_frame_count(m);
  } else if(!strcmp(x, "wav")) {
    drwav* w = malloc(sizeof *w); if(!drwav_init_file(w, path, NULL)) { free(w); return 0; }
    s->type = T_WAV; s->h = w; s->rate = w->sampleRate; s->ch = w->channels; s->len = w->totalPCMFrameCount;
  } else if(!strcmp(x, "pcm")) {
    FILE* f = fopen(path, "rb"); if(!f) return 0;
    unsigned char hd[8];
    if(fread(hd, 1, 8, f) != 8 || memcmp(hd, "MSU1", 4)) { fclose(f); return 0; }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 8, SEEK_SET);
    s->type = T_PCM; s->f = f; s->rate = 44100; s->ch = 2; s->len = (uint64_t)(n - 8) / 4;
    s->loopStart = hd[4] | hd[5] << 8 | hd[6] << 16 | (uint32_t)hd[7] << 24;
  } else return 0;
  if(s->ch < 1 || s->rate < 8000) { src_close(s); return 0; }
  if(s->type != T_PCM && s->type != T_OGG) read_sidecar(s, path);
  else if(s->type == T_OGG && !s->loopStart && !s->loopEnd) read_sidecar(s, path);
  if(s->loopEnd > s->len || s->loopEnd <= s->loopStart) s->loopEnd = 0;
  if(s->loopStart >= s->len) s->loopStart = 0;
  return 1;
}
static void src_seek(Src* s, uint64_t p) {
  if(p > s->len) p = s->len;
  switch(s->type) {
    case T_OGG: stb_vorbis_seek(s->h, (unsigned)p); break;
    case T_FLAC: drflac_seek_to_pcm_frame(s->h, p); break;
    case T_MP3: drmp3_seek_to_pcm_frame(s->h, p); break;
    case T_WAV: drwav_seek_to_pcm_frame(s->h, p); break;
    case T_PCM: fseek(s->f, 8 + (long)p * 4, SEEK_SET); break;
  }
  s->pos = p;
}
// read up to n frames as stereo s16; returns frames read (0 at the end)
static int src_read(Src* s, int16_t* out, int n) {
  int got = 0;
  if(s->type == T_PCM) {
    got = (int)fread(out, 4, n, s->f);
  } else {
    static int16_t tmp[4096 * 8];
    int ch = s->ch > 8 ? 8 : s->ch; if(n > 4096) n = 4096;
    switch(s->type) {
      case T_OGG: got = stb_vorbis_get_samples_short_interleaved(s->h, 2, out, n * 2); ch = 2; break;
      case T_FLAC: got = (int)drflac_read_pcm_frames_s16(s->h, n, tmp); break;
      case T_MP3: got = (int)drmp3_read_pcm_frames_s16(s->h, n, tmp); break;
      case T_WAV: got = (int)drwav_read_pcm_frames_s16(s->h, n, tmp); break;
    }
    if(s->type != T_OGG) for(int i = 0; i < got; i++) {
      out[2 * i] = tmp[i * s->ch]; out[2 * i + 1] = tmp[i * s->ch + (s->ch > 1 ? 1 : 0)];
    }
    (void)ch;
  }
  s->pos += got;
  return got;
}
// the next source frame, looping or ending the track
static int16_t rb[2 * 1024]; static int rbN, rbI;
static int next_frame(int16_t* f) {
  for(int tries = 0; tries < 3; tries++) {
    uint64_t end = src.loopEnd ? src.loopEnd : src.len;
    if(rbI < rbN && src.pos - (rbN - rbI) < end) { f[0] = rb[2 * rbI]; f[1] = rb[2 * rbI + 1]; rbI++; return 1; }
    if(src.pos - (rbN - rbI) >= end || (rbI >= rbN && src.pos >= end)) {
      if(!repeat) return 0;
      src_seek(&src, src.loopStart); rbN = rbI = 0; continue;
    }
    int want = 1024; if(src.pos + want > end) want = (int)(end - src.pos);
    rbN = src_read(&src, rb, want); rbI = 0;
    if(rbN <= 0) {                                         // decoder ended early: treat as the end
      rbN = 0; if(!repeat) return 0;
      src_seek(&src, src.loopStart); continue;
    }
  }
  return 0;
}
static uint64_t play_pos(void) { return src.pos - (rbN - rbI); }

// ---------------------------------------------------------------- the chip
void music_stop(void) {
  if(src.type) src_close(&src);
  track = 0; playing = 0; rbN = rbI = 0;
}
static void load_track(int t) {
  music_note_request(t);
  if(src.type && t == track) { missing = !enabled; return; }   // the same track again: keep it (and its position)
  // going back to the track before this one (map music after a battle): carry on where it was
  int back = t == prevTrack ? 1 : 0; uint64_t backPos = prevPos;
  if(src.type && track) { prevTrack = track; prevPos = play_pos(); }
  music_stop();
  missing = 1;
  if(!enabled || !music_file(t)) return;
  if(!src_open(&src, music_file(t))) { fprintf(stderr, "music: couldn't open %s\n", music_file(t)); return; }
  track = t; missing = 0;
  src_seek(&src, back && backPos < src.len ? backPos : 0);
  frac = 0; next_frame(cur); next_frame(nxt);
}
uint8_t music_read(uint16_t adr) {
  switch(adr & 7) {
    case 0: return (uint8_t)((playing ? 0x10 : 0) | (repeat ? 0x20 : 0) | (missing ? 0x08 : 0) | 2);
    case 1: return 0;
    default: return (uint8_t)"S-MSU1"[(adr & 7) - 2];
  }
}
void music_write(uint16_t adr, uint8_t v) {
  switch(adr & 7) {
    case 4: reqTrack = (reqTrack & 0xff00) | v; break;
    case 5: reqTrack = (reqTrack & 0xff) | v << 8; load_track(reqTrack); break;
    case 6: vol = v; break;
    case 7:
      if(!src.type) { playing = 0; break; }
      repeat = (v & 2) != 0;
      if(v & 1) {
        playing = 1;
      } else { if(playing) { prevTrack = track; prevPos = play_pos(); } playing = 0; }
      break;
  }
}

void music_mix(int16_t* buf, int n, int volume) {
  if(!playing || !src.type) return;
  double step = (double)src.rate / 48000.0;
  float target = vol / 255.0f * volume / 100.0f;
  for(int i = 0; i < n; i++) {
    if(target == 0.0f) { curVol -= 1.0f / (0.6f * 48000); if(curVol < 0) curVol = 0; }   // fade out (the game's fades)
    else curVol += (target - curVol) * 0.002f;            // other changes: quick and smooth (no clicks)
    float l = cur[0] + (nxt[0] - cur[0]) * (float)frac, r = cur[1] + (nxt[1] - cur[1]) * (float)frac;
    int a = buf[2 * i] + (int)(l * curVol), b = buf[2 * i + 1] + (int)(r * curVol);
    buf[2 * i] = (int16_t)(a > 32767 ? 32767 : a < -32768 ? -32768 : a);
    buf[2 * i + 1] = (int16_t)(b > 32767 ? 32767 : b < -32768 ? -32768 : b);
    frac += step;
    while(frac >= 1.0) {
      frac -= 1.0; cur[0] = nxt[0]; cur[1] = nxt[1];
      if(!next_frame(nxt)) { playing = 0; return; }
    }
  }
}

// ---------------------------------------------------------------- save states
typedef struct { char tag[4]; int32_t track, playing, repeat, vol, prevTrack; uint64_t pos, prevPos; } MState;
int music_state_size(void) { return sizeof(MState); }
void music_state_save(uint8_t* d) {
  MState m = { { 'M', 'S', 'U', '1' }, track, playing, repeat, vol, prevTrack, src.type ? play_pos() : 0, prevPos };
  memcpy(d, &m, sizeof m);
}
void music_state_load(const uint8_t* d, int n) {
  MState m; music_stop();
  if(n < (int)sizeof m || memcmp(d, "MSU1", 4)) return;
  memcpy(&m, d, sizeof m);
  prevTrack = m.prevTrack; prevPos = m.prevPos; vol = m.vol; repeat = m.repeat;
  if(m.track && enabled && music_file(m.track) && src_open(&src, music_file(m.track))) {
    track = m.track; missing = 0; src_seek(&src, m.pos); frac = 0; next_frame(cur); next_frame(nxt);
    playing = m.playing; curVol = vol / 255.0f;
  }
}

// ---------------------------------------------------------------- MSU-1 .pcm for emulators
// any track the port can play -> 44.1 kHz stereo 16-bit with the "MSU1" header and its loop point
int music_convert(const char* in, const char* out, char* err, int errn) {
  Src s;
  const char* base = strrchr(in, '/'); const char* b2 = strrchr(in, '\\');
  if(b2 > base) base = b2;
  base = base ? base + 1 : in;
  if(!src_open_path(&s, in, base)) { snprintf(err, errn, "can't read %s (ogg, flac, mp3, wav or pcm)", in); return 0; }
  FILE* f = fopen(out, "wb");
  if(!f) { snprintf(err, errn, "can't write %s", out); src_close(&s); return 0; }
  double step = s.rate / 44100.0;
  uint64_t end = s.loopEnd ? s.loopEnd : s.len;
  uint32_t loop = (uint32_t)(s.loopStart / step);
  unsigned char hd[8] = { 'M', 'S', 'U', '1', loop & 255, loop >> 8 & 255, loop >> 16 & 255, loop >> 24 & 255 };
  fwrite(hd, 1, 8, f);
  static int16_t ib[2 * 4096];
  int n = 0, k = 0; uint64_t got = 0;
  #define NEXT_FRAME(fr) ( (k < n || (got < end && (n = src_read(&s, ib, (int)(end - got < 4096 ? end - got : 4096)), k = 0, n > 0))) \
      ? ((fr)[0] = ib[2 * k], (fr)[1] = ib[2 * k + 1], k++, got++, 1) : 0 )
  int16_t cur[2], nxt[2];
  if(NEXT_FRAME(cur)) {
    if(!NEXT_FRAME(nxt)) { nxt[0] = cur[0]; nxt[1] = cur[1]; }
    double frac = 0; int more = 1;
    static int16_t ob[2 * 4096]; int m = 0;
    while(more) {
      ob[m++] = (int16_t)(cur[0] + (nxt[0] - cur[0]) * frac); ob[m++] = (int16_t)(cur[1] + (nxt[1] - cur[1]) * frac);
      if(m == 2 * 4096) { fwrite(ob, 2, m, f); m = 0; }
      frac += step;
      while(frac >= 1.0) { frac -= 1.0; cur[0] = nxt[0]; cur[1] = nxt[1]; if(!NEXT_FRAME(nxt)) { more = 0; break; } }
    }
    fwrite(ob, 2, m, f);
  }
  #undef NEXT_FRAME
  fclose(f); src_close(&s);
  return 1;
}
