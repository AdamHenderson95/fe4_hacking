// Custom music: an MSU-1 audio chip for the port, playing tracks from the music folder.
// The game asks for a song through a small patch (fe4music_patch.h); a song with a file in the folder
// plays that file, the others play the game's own music as before.
#ifndef FE4_MUSIC_H
#define FE4_MUSIC_H
#include <stdint.h>

void music_init(const char* dir);          // the music folder (ends with a slash); scans it
void music_rescan(void);
const char* music_dir(void);
int  music_count(void);                    // tracks found
const char* music_file(int track);         // file name for a track number, or NULL
void music_set_enabled(int on);            // off: the chip isn't there, the game plays its own music
int  music_enabled(void);

// the chip's registers ($2000-$2007)
uint8_t music_read(uint16_t adr);
void music_write(uint16_t adr, uint8_t v);

// add n stereo frames at 48 kHz to buf (volume 0-100 for the music alone)
void music_mix(int16_t* buf, int n, int volume);
int  music_playing(void);                  // track number playing from a file, 0 = none
int  music_last_request(void);             // the last song the game asked for (any song)
void music_note_request(int song);

// save states: the chip's state next to the game's
int  music_state_size(void);
void music_state_save(uint8_t* d);
void music_state_load(const uint8_t* d, int n);
void music_stop(void);
// write an MSU-1 track (44.1 kHz .pcm with its loop point) from any file the port can play
int  music_convert(const char* in, const char* out, char* err, int errn);
#endif
