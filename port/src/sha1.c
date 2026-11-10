// Minimal SHA-1 (for ROM identification).
#include <stdint.h>
#include <string.h>
#include "sha1.h"

#define ROL(v, n) (((v) << (n)) | ((v) >> (32 - (n))))

static void block(uint32_t h[5], const uint8_t* p) {
  uint32_t w[80];
  for(int i = 0; i < 16; i++) w[i] = (p[i * 4] << 24) | (p[i * 4 + 1] << 16) | (p[i * 4 + 2] << 8) | p[i * 4 + 3];
  for(int i = 16; i < 80; i++) w[i] = ROL(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
  uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
  for(int i = 0; i < 80; i++) {
    uint32_t f, k;
    if(i < 20) { f = (b & c) | (~b & d); k = 0x5A827999; }
    else if(i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
    else if(i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
    else { f = b ^ c ^ d; k = 0xCA62C1D6; }
    uint32_t t = ROL(a, 5) + f + e + k + w[i];
    e = d; d = c; c = ROL(b, 30); b = a; a = t;
  }
  h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
}

void sha1(const uint8_t* data, size_t len, char hex[41]) {
  uint32_t h[5] = { 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0 };
  size_t i = 0;
  for(; i + 64 <= len; i += 64) block(h, data + i);
  uint8_t tail[128] = { 0 };
  size_t rem = len - i;
  memcpy(tail, data + i, rem);
  tail[rem] = 0x80;
  size_t tl = rem < 56 ? 64 : 128;
  uint64_t bits = (uint64_t)len * 8;
  for(int j = 0; j < 8; j++) tail[tl - 1 - j] = bits >> (j * 8);
  block(h, tail);
  if(tl == 128) block(h, tail + 64);
  static const char* X = "0123456789abcdef";
  for(int j = 0; j < 20; j++) { uint8_t v = h[j / 4] >> (24 - (j % 4) * 8); hex[j * 2] = X[v >> 4]; hex[j * 2 + 1] = X[v & 15]; }
  hex[40] = 0;
}
