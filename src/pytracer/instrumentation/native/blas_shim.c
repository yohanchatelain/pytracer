/* Pytracer T5 — native BLAS/LAPACK kernel census (LD_PRELOAD shim).
 *
 * Interposes the hot GEMM/GESV entry points and appends one line per call
 * ("<symbol> <m> <n> <k>") to the file named by PYTRACER_NATIVE_LOG, then
 * forwards to the real symbol via dlsym(RTLD_NEXT, ...). This is a census
 * (which kernels ran, how big), not a value tracer.
 *
 * Two naming conventions are covered:
 *  - standard 32-bit-int BLAS (system OpenBLAS, netlib, MKL LP64):
 *      cblas_dgemm, cblas_sgemm, dgemm_, sgemm_, dgesv_
 *  - the scipy-openblas bundled in numpy/scipy wheels (prefixed, ILP64):
 *      scipy_cblas_dgemm64_, scipy_cblas_sgemm64_, scipy_dgemm_64_,
 *      scipy_sgemm_64_, scipy_dgesv_64_
 *
 * Fortran-convention entries declare two trailing size_t parameters for the
 * hidden character-length arguments gfortran callers pass; C-implemented
 * BLAS ignores them, so forwarding them is safe in both worlds.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define LOG_BUFFER_SIZE 65536

struct log_buffer {
    size_t used;
    char data[LOG_BUFFER_SIZE];
};

static int log_fd = -1;
static _Atomic int log_failed = 0;
static int log_key_ready = 0;
static pthread_key_t log_key;
static pthread_once_t log_once = PTHREAD_ONCE_INIT;

static void write_all(const char *data, size_t size) {
    while (size > 0 && log_fd >= 0) {
        ssize_t written = write(log_fd, data, size);
        if (written > 0) {
            data += written;
            size -= (size_t)written;
        } else if (written < 0 && errno == EINTR) {
            continue;
        } else {
            log_failed = 1;
            return;
        }
    }
}

static void flush_buffer(void *value) {
    struct log_buffer *buffer = (struct log_buffer *)value;
    if (buffer && buffer->used > 0) {
        write_all(buffer->data, buffer->used);
        buffer->used = 0;
    }
}

static void destroy_buffer(void *value) {
    flush_buffer(value);
    free(value);
}

static void close_log(void) {
    if (log_key_ready) {
        struct log_buffer *buffer = pthread_getspecific(log_key);
        if (buffer) {
            flush_buffer(buffer);
            pthread_setspecific(log_key, NULL);
            free(buffer);
        }
    }
    if (log_fd >= 0) {
        close(log_fd);
        log_fd = -1;
    }
}

static void init_log(void) {
    const char *path = getenv("PYTRACER_NATIVE_LOG");
    if (!path) {
        log_failed = 1;
        return;
    }
    log_fd = open(path, O_CREAT | O_WRONLY | O_APPEND, 0666);
    if (log_fd < 0 || pthread_key_create(&log_key, destroy_buffer) != 0) {
        if (log_fd >= 0) close(log_fd);
        log_fd = -1;
        log_failed = 1;
        return;
    }
    log_key_ready = 1;
    atexit(close_log);
}

static struct log_buffer *get_log_buffer(void) {
    struct log_buffer *buffer = pthread_getspecific(log_key);
    if (!buffer) {
        buffer = (struct log_buffer *)calloc(1, sizeof(*buffer));
        if (!buffer || pthread_setspecific(log_key, buffer) != 0) {
            free(buffer);
            log_failed = 1;
            return NULL;
        }
    }
    return buffer;
}

static void log_call(const char *name, long long m, long long n, long long k) {
    pthread_once(&log_once, init_log);
    if (log_failed || log_fd < 0) return;

    char line[128];
    int length = snprintf(line, sizeof(line), "%s %lld %lld %lld\n", name, m, n, k);
    if (length <= 0) return;
    size_t size = (size_t)length;
    if (size >= sizeof(line)) size = sizeof(line) - 1;

    struct log_buffer *buffer = get_log_buffer();
    if (!buffer) return;
    if (buffer->used + size > LOG_BUFFER_SIZE) flush_buffer(buffer);
    memcpy(buffer->data + buffer->used, line, size);
    buffer->used += size;
}

/* Resolve the real symbol. RTLD_NEXT fails when the real BLAS was loaded
 * RTLD_LOCAL (numpy/scipy wheels dlopen their bundled openblas that way:
 * our shim still intercepts the PLT binding of dependent modules, but the
 * real symbol is invisible to global lookup). Fall back to the library
 * paths supplied by pytracer in PYTRACER_NATIVE_REAL_LIBS (colon-separated),
 * skipping our own interposer to avoid infinite recursion. */
static void *resolve(const char *name, void *self) {
    void *fn = dlsym(RTLD_NEXT, name);
    if (fn && fn != self) return fn;
    fn = dlsym(RTLD_DEFAULT, name);
    if (fn && fn != self) return fn;
    const char *libs = getenv("PYTRACER_NATIVE_REAL_LIBS");
    if (libs) {
        char buf[4096];
        snprintf(buf, sizeof(buf), "%s", libs);
        char *save = NULL;
        for (char *path = strtok_r(buf, ":", &save); path;
             path = strtok_r(NULL, ":", &save)) {
            void *handle = dlopen(path, RTLD_LAZY | RTLD_NOLOAD);
            if (!handle) handle = dlopen(path, RTLD_LAZY);
            if (!handle) continue;
            fn = dlsym(handle, name);
            if (fn && fn != self) return fn;
        }
    }
    fprintf(stderr, "pytracer blas_shim: cannot resolve real %s; aborting to "
                    "avoid silent corruption (set PYTRACER_NATIVE_REAL_LIBS)\n",
            name);
    abort();
}

/* ---- CBLAS, 32-bit integers ------------------------------------------- */

typedef void (*cblas_dgemm32_t)(int, int, int, int, int, int, double,
                                const void *, int, const void *, int, double,
                                void *, int);
void cblas_dgemm(int order, int ta, int tb, int m, int n, int k, double alpha,
                 const void *a, int lda, const void *b, int ldb, double beta,
                 void *c, int ldc) {
    static cblas_dgemm32_t fn = NULL;
    if (!fn) fn = (cblas_dgemm32_t)resolve("cblas_dgemm", (void *)cblas_dgemm);
    log_call("cblas_dgemm", m, n, k);
    fn(order, ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc);
}

typedef void (*cblas_sgemm32_t)(int, int, int, int, int, int, float,
                                const void *, int, const void *, int, float,
                                void *, int);
void cblas_sgemm(int order, int ta, int tb, int m, int n, int k, float alpha,
                 const void *a, int lda, const void *b, int ldb, float beta,
                 void *c, int ldc) {
    static cblas_sgemm32_t fn = NULL;
    if (!fn) fn = (cblas_sgemm32_t)resolve("cblas_sgemm", (void *)cblas_sgemm);
    log_call("cblas_sgemm", m, n, k);
    fn(order, ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc);
}

/* ---- CBLAS, scipy-openblas ILP64 (numpy/scipy wheels) ------------------ */

typedef void (*cblas_dgemm64_t)(int, int, int, int64_t, int64_t, int64_t,
                                double, const void *, int64_t, const void *,
                                int64_t, double, void *, int64_t);
void scipy_cblas_dgemm64_(int order, int ta, int tb, int64_t m, int64_t n,
                          int64_t k, double alpha, const void *a, int64_t lda,
                          const void *b, int64_t ldb, double beta, void *c,
                          int64_t ldc) {
    static cblas_dgemm64_t fn = NULL;
    if (!fn) fn = (cblas_dgemm64_t)resolve("scipy_cblas_dgemm64_", (void *)scipy_cblas_dgemm64_);
    log_call("scipy_cblas_dgemm64_", (long long)m, (long long)n, (long long)k);
    fn(order, ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc);
}

typedef void (*cblas_sgemm64_t)(int, int, int, int64_t, int64_t, int64_t,
                                float, const void *, int64_t, const void *,
                                int64_t, float, void *, int64_t);
void scipy_cblas_sgemm64_(int order, int ta, int tb, int64_t m, int64_t n,
                          int64_t k, float alpha, const void *a, int64_t lda,
                          const void *b, int64_t ldb, float beta, void *c,
                          int64_t ldc) {
    static cblas_sgemm64_t fn = NULL;
    if (!fn) fn = (cblas_sgemm64_t)resolve("scipy_cblas_sgemm64_", (void *)scipy_cblas_sgemm64_);
    log_call("scipy_cblas_sgemm64_", (long long)m, (long long)n, (long long)k);
    fn(order, ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc);
}

/* ---- Fortran convention, 32-bit integers ------------------------------- */

typedef void (*f_dgemm32_t)(const char *, const char *, const int *,
                            const int *, const int *, const double *,
                            const double *, const int *, const double *,
                            const int *, const double *, double *, const int *,
                            size_t, size_t);
void dgemm_(const char *ta, const char *tb, const int *m, const int *n,
            const int *k, const double *alpha, const double *a, const int *lda,
            const double *b, const int *ldb, const double *beta, double *c,
            const int *ldc, size_t lta, size_t ltb) {
    static f_dgemm32_t fn = NULL;
    if (!fn) fn = (f_dgemm32_t)resolve("dgemm_", (void *)dgemm_);
    log_call("dgemm_", *m, *n, *k);
    fn(ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc, lta, ltb);
}

typedef void (*f_dgesv32_t)(const int *, const int *, double *, const int *,
                            int *, double *, const int *, int *);
void dgesv_(const int *n, const int *nrhs, double *a, const int *lda,
            int *ipiv, double *b, const int *ldb, int *info) {
    static f_dgesv32_t fn = NULL;
    if (!fn) fn = (f_dgesv32_t)resolve("dgesv_", (void *)dgesv_);
    log_call("dgesv_", *n, *nrhs, 0);
    fn(n, nrhs, a, lda, ipiv, b, ldb, info);
}

/* ---- Fortran convention, scipy-openblas ILP64 --------------------------- */

typedef void (*f_dgemm64_t)(const char *, const char *, const int64_t *,
                            const int64_t *, const int64_t *, const double *,
                            const double *, const int64_t *, const double *,
                            const int64_t *, const double *, double *,
                            const int64_t *, size_t, size_t);
void scipy_dgemm_64_(const char *ta, const char *tb, const int64_t *m,
                     const int64_t *n, const int64_t *k, const double *alpha,
                     const double *a, const int64_t *lda, const double *b,
                     const int64_t *ldb, const double *beta, double *c,
                     const int64_t *ldc, size_t lta, size_t ltb) {
    static f_dgemm64_t fn = NULL;
    if (!fn) fn = (f_dgemm64_t)resolve("scipy_dgemm_64_", (void *)scipy_dgemm_64_);
    log_call("scipy_dgemm_64_", (long long)*m, (long long)*n, (long long)*k);
    fn(ta, tb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc, lta, ltb);
}

typedef void (*f_dgesv64_t)(const int64_t *, const int64_t *, double *,
                            const int64_t *, int64_t *, double *,
                            const int64_t *, int64_t *);
void scipy_dgesv_64_(const int64_t *n, const int64_t *nrhs, double *a,
                     const int64_t *lda, int64_t *ipiv, double *b,
                     const int64_t *ldb, int64_t *info) {
    static f_dgesv64_t fn = NULL;
    if (!fn) fn = (f_dgesv64_t)resolve("scipy_dgesv_64_", (void *)scipy_dgesv_64_);
    log_call("scipy_dgesv_64_", (long long)*n, (long long)*nrhs, 0);
    fn(n, nrhs, a, lda, ipiv, b, ldb, info);
}
