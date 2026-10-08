#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#define DYLD_INTERPOSE(replacement, original) \
  __attribute__((used)) static const struct { const void *replacement; const void *original; } \
  interpose_##original __attribute__((section("__DATA,__interpose"))) = \
  { (const void *)&replacement, (const void *)&original };
extern void mpi_finalize_(int *);
static void mark(const char *event, int value) {
  int saved = errno;
  if (strcmp(getprogname(), "wrf.exe") == 0) {
    char buf[160]; int n = snprintf(buf, sizeof(buf), "KDM_EXIT_OBSERVER pid=%ld event=%s value=%d\n", (long)getpid(), event, value);
    if (n > 0 && n < (int)sizeof(buf)) (void)write(2, buf, (size_t)n);
  }
  errno = saved;
}
__attribute__((constructor)) static void loaded(void) { mark("loaded", 0); }
static void trace_finalize(int *ierr) {
  mark("mpi_finalize_enter", 0);
  mpi_finalize_(ierr);
  mark("mpi_finalize_return", ierr ? *ierr : -999);
}
__attribute__((noreturn)) static void trace_Exit(int status) { mark("_Exit", status); _Exit(status); }
__attribute__((noreturn)) static void trace_abort(void) { mark("abort", 0); abort(); }
DYLD_INTERPOSE(trace_finalize, mpi_finalize_)
DYLD_INTERPOSE(trace_Exit, _Exit)
DYLD_INTERPOSE(trace_abort, abort)
