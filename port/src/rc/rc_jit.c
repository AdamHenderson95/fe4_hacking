// Compiles the recompiled C in memory with libtcc and returns its block table.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libtcc.h"
#include "rc_jit.h"
#include "rc_gen.h"

static const char rc_gen_h_text[] =
#include "rc_gen_h.inc"
;

static char jit_err[4096];
static void on_err(void* opaque, const char* msg) {
  (void)opaque;
  size_t n = strlen(jit_err);
  if(n < sizeof jit_err - 2) snprintf(jit_err + n, sizeof jit_err - n, "%s\n", msg);
}
const char* rc_jitError(void) { return jit_err; }

int rc_jitCompile(const char* source, const RcEntry** blocks, int* count, void** handle) {
  jit_err[0] = 0;
  TCCState* s = tcc_new();
  if(!s) { strcpy(jit_err, "tcc_new failed"); return 0; }
  tcc_set_error_func(s, NULL, on_err);
  tcc_set_options(s, "-nostdlib -nostdinc");
  tcc_define_symbol(s, "RC_GEN_INLINE", "1");
  tcc_set_output_type(s, TCC_OUTPUT_MEMORY);
  size_t hl = strlen(rc_gen_h_text), sl = strlen(source);
  char* all = malloc(hl + sl + 2);
  memcpy(all, rc_gen_h_text, hl); all[hl] = '\n'; memcpy(all + hl + 1, source, sl + 1);
  int r = tcc_compile_string(s, all);
  free(all);
  if(r < 0) { tcc_delete(s); return 0; }
#define SYM(f) tcc_add_symbol(s, #f, (const void*)f)
  SYM(rcR); SYM(rcW); SYM(rcI); SYM(rcF); SYM(rcCI); SYM(rcRW); SYM(rcWW); SYM(rcP8); SYM(rcP16);
  SYM(rcL8); SYM(rcL16); SYM(rcGF); SYM(rcSF); SYM(rcIMP); SYM(rcADC8); SYM(rcADC16); SYM(rcSBC8); SYM(rcSBC16);
#undef SYM
  if(tcc_relocate(s) < 0) { tcc_delete(s); return 0; }
  const RcEntry* tab = tcc_get_symbol(s, "rc_blocks");
  const int* n = tcc_get_symbol(s, "rc_blockCountGen");
  if(!tab || !n) { strcpy(jit_err, "block table missing"); tcc_delete(s); return 0; }
  const int* lay = tcc_get_symbol(s, "rc_layout");
  if(!lay || lay[0] != (int)sizeof(RcCpu) || lay[1] != (int)(long long)&((RcCpu*)0)->icount || lay[2] != (int)(long long)&((RcCpu*)0)->brk) {
    strcpy(jit_err, "compiled code disagrees with the runtime about the CPU layout"); tcc_delete(s); return 0;
  }
  *blocks = tab; *count = *n; *handle = s;
  return 1;
}

void rc_jitFree(void* handle) { if(handle) tcc_delete((TCCState*)handle); }
