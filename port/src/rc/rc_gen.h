// Interface between recompiled FE4 code and the port runtime.
// Self-contained (no system headers) so it can be compiled by the bundled TinyCC.
#ifndef RC_GEN_H
#define RC_GEN_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef unsigned long long u64;

// Must match struct Cpu in snes/cpu.h exactly (checked by static asserts in rc_rt.c).
typedef struct RcCpu {
  void* mem; void* read; void* write; void* idle;
  u16 a, x, y, sp, pc, dp;
  u8 k, db;
  _Bool c, z, v, n, i, d, xf, mf, e;
  _Bool waiting, stopped;
  _Bool irqWanted, nmiWanted, intWanted, intDelay, resetWanted;
  _Bool brk;
  u64 icount;
} RcCpu;

typedef void (*RcBlockFn)(RcCpu* c);
typedef struct RcEntry { u32 pc; u32 fs; RcBlockFn fn; } RcEntry;

// bus access, exactly as the interpreter performs it
u8   rcR(RcCpu* c, u32 adr);                    // data read
void rcW(RcCpu* c, u32 adr, u8 v);              // data write
void rcI(RcCpu* c);                             // internal (idle) cycle
void rcF(RcCpu* c, u32 adr, u8 v);              // fetch of a known ROM byte (timing + open bus)
void rcCI(RcCpu* c);                            // interrupt poll point
u16  rcRW(RcCpu* c, u32 lo, u32 hi, int ic);    // 16-bit read (poll between bytes if ic)
void rcWW(RcCpu* c, u32 lo, u32 hi, u16 v, int rev, int ic);
void rcP8(RcCpu* c, u8 v);                      // push
void rcP16(RcCpu* c, u16 v, int ic);
u8   rcL8(RcCpu* c);                            // pull
u16  rcL16(RcCpu* c, int ic);
u8   rcGF(RcCpu* c);                            // P register get/set
void rcSF(RcCpu* c, u8 v);
void rcIMP(RcCpu* c, u32 nextAdr, u8 nextByte); // 2-cycle implied op's idle/poll cycle
// arithmetic
void rcADC8(RcCpu* c, u8 v);
void rcADC16(RcCpu* c, u16 v);
void rcSBC8(RcCpu* c, u8 v);
void rcSBC16(RcCpu* c, u16 v);

#define ZN8(val)  (c->z = (((val) & 0xff) == 0), c->n = (((val) & 0x80) != 0))
#define ZN16(val) (c->z = (((val) & 0xffff) == 0), c->n = (((val) & 0x8000) != 0))
#define DB ((u32)c->db << 16)
// end of an instruction inside a block: leave if an interrupt or frame event is pending
#define NEXT(npc) c->icount++; if(c->intWanted | c->brk) { c->pc = (npc); return; }
#define DPX if(c->dp & 0xff) rcI(c)

#endif
