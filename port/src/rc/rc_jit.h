#ifndef RC_JIT_H
#define RC_JIT_H
#include "rc_gen.h"
// compile generated source in memory; on success fills the block table and an opaque handle
int rc_jitCompile(const char* source, const RcEntry** blocks, int* count, void** handle);
const char* rc_jitError(void);
void rc_jitFree(void* handle);
#endif
