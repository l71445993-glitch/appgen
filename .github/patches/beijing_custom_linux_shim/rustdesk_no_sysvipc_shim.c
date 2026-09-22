#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/shm.h>

typedef struct xcb_connection_t xcb_connection_t;
typedef uint32_t xcb_drawable_t;
typedef uint32_t xcb_shm_seg_t;
typedef uint32_t xcb_visualid_t;

typedef struct {
    unsigned int sequence;
} xcb_void_cookie_t;

typedef struct {
    unsigned int sequence;
} xcb_shm_get_image_cookie_t;

typedef struct {
    unsigned int sequence;
} xcb_get_image_cookie_t;

typedef struct {
    uint8_t response_type;
    uint8_t error_code;
    uint16_t sequence;
    uint32_t resource_id;
    uint16_t minor_code;
    uint8_t major_code;
    uint8_t pad0;
    uint32_t pad[5];
    uint32_t full_sequence;
} xcb_generic_error_t;

typedef struct {
    uint8_t response_type;
    uint8_t depth;
    uint16_t sequence;
    uint32_t length;
    xcb_visualid_t visual;
    uint32_t size;
} xcb_shm_get_image_reply_t;

typedef struct {
    uint8_t response_type;
    uint8_t depth;
    uint16_t sequence;
    uint32_t length;
    xcb_visualid_t visual;
    uint8_t pad0[20];
} xcb_get_image_reply_t;

_Static_assert(sizeof(xcb_void_cookie_t) == 4, "unexpected xcb cookie ABI");
_Static_assert(sizeof(xcb_shm_get_image_cookie_t) == 4,
               "unexpected xcb-shm cookie ABI");
_Static_assert(sizeof(xcb_get_image_cookie_t) == 4,
               "unexpected xcb get_image cookie ABI");
_Static_assert(sizeof(xcb_shm_get_image_reply_t) == 16,
               "unexpected xcb_shm_get_image_reply_t ABI");
_Static_assert(sizeof(xcb_get_image_reply_t) == 32,
               "unexpected xcb_get_image_reply_t ABI");

typedef int (*real_shmget_fn)(key_t, size_t, int);
typedef void *(*real_shmat_fn)(int, const void *, int);
typedef int (*real_shmdt_fn)(const void *);
typedef int (*real_shmctl_fn)(int, int, struct shmid_ds *);

#define shim_old_dlsym dlsym
#define shim_old_dlopen dlopen

typedef xcb_void_cookie_t (*real_xcb_shm_attach_fn)(xcb_connection_t *,
                                                    xcb_shm_seg_t, uint32_t,
                                                    uint8_t);
typedef xcb_void_cookie_t (*real_xcb_shm_detach_fn)(xcb_connection_t *,
                                                    xcb_shm_seg_t);
typedef xcb_shm_get_image_cookie_t (*real_xcb_shm_get_image_unchecked_fn)(
    xcb_connection_t *, xcb_drawable_t, int16_t, int16_t, uint16_t, uint16_t,
    uint32_t, uint8_t, xcb_shm_seg_t, uint32_t);
typedef xcb_shm_get_image_reply_t *(*real_xcb_shm_get_image_reply_fn)(
    xcb_connection_t *, xcb_shm_get_image_cookie_t, xcb_generic_error_t **);
typedef xcb_get_image_cookie_t (*real_xcb_get_image_fn)(
    xcb_connection_t *, uint8_t, xcb_drawable_t, int16_t, int16_t, uint16_t,
    uint16_t, uint32_t);
typedef xcb_get_image_reply_t *(*real_xcb_get_image_reply_fn)(
    xcb_connection_t *, xcb_get_image_cookie_t, xcb_generic_error_t **);
typedef uint8_t *(*real_xcb_get_image_data_fn)(const xcb_get_image_reply_t *);
typedef int (*real_xcb_get_image_data_length_fn)(const xcb_get_image_reply_t *);

typedef struct FakeShm {
    int id;
    size_t size;
    uint8_t *buffer;
    int attached_count;
    int removed;
    struct FakeShm *next;
} FakeShm;

typedef struct FakeXcbSeg {
    xcb_connection_t *connection;
    xcb_shm_seg_t xcbid;
    FakeShm *shm;
    struct FakeXcbSeg *next;
} FakeXcbSeg;

typedef struct PendingImage {
    unsigned int sequence;
    xcb_connection_t *connection;
    xcb_drawable_t drawable;
    int16_t x;
    int16_t y;
    uint16_t width;
    uint16_t height;
    uint32_t plane_mask;
    uint8_t format;
    xcb_shm_seg_t xcbid;
    uint32_t offset;
    struct PendingImage *next;
} PendingImage;

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static FakeShm *g_fake_shm;
static FakeXcbSeg *g_fake_xcb;
static PendingImage *g_pending;
static int g_next_shmid = 0x52440000;
static unsigned int g_next_sequence = 0x53480000U;

static int log_enabled(void) {
    static int checked;
    static int enabled;

    if (!checked) {
        const char *env = getenv("RUSTDESK_NO_SYSVIPC_SHIM_LOG");
        enabled = env && env[0] && strcmp(env, "0") != 0;
        checked = 1;
    }
    return enabled;
}

static void shim_log(const char *fmt, ...) {
    if (!log_enabled()) {
        return;
    }

    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[rustdesk-no-sysvipc-shim] ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
}

static void *lookup_symbol(const char *name, const char *fallback_library) {
    void *symbol = shim_old_dlsym(RTLD_NEXT, name);
    if (!symbol && fallback_library) {
        void *handle = shim_old_dlopen(fallback_library, RTLD_LAZY | RTLD_GLOBAL);
        if (handle) {
            symbol = shim_old_dlsym(handle, name);
        }
    }
    return symbol;
}

static FakeShm *find_fake_shm_locked(int shmid) {
    for (FakeShm *item = g_fake_shm; item; item = item->next) {
        if (item->id == shmid) {
            return item;
        }
    }
    return NULL;
}

static FakeShm *find_fake_shm_by_addr_locked(const void *addr) {
    for (FakeShm *item = g_fake_shm; item; item = item->next) {
        if (item->buffer == (const uint8_t *)addr) {
            return item;
        }
    }
    return NULL;
}

static FakeXcbSeg *find_fake_xcb_locked(xcb_connection_t *connection,
                                        xcb_shm_seg_t xcbid) {
    for (FakeXcbSeg *item = g_fake_xcb; item; item = item->next) {
        if (item->connection == connection && item->xcbid == xcbid) {
            return item;
        }
    }
    return NULL;
}

static PendingImage *take_pending_locked(xcb_connection_t *connection,
                                         unsigned int sequence) {
    PendingImage **link = &g_pending;
    while (*link) {
        PendingImage *item = *link;
        if (item->connection == connection && item->sequence == sequence) {
            *link = item->next;
            item->next = NULL;
            return item;
        }
        link = &item->next;
    }
    return NULL;
}

static void remove_xcb_segments_for_shm_locked(FakeShm *shm) {
    FakeXcbSeg **link = &g_fake_xcb;
    while (*link) {
        FakeXcbSeg *item = *link;
        if (item->shm == shm) {
            *link = item->next;
            free(item);
            continue;
        }
        link = &item->next;
    }
}

static void maybe_free_fake_shm_locked(FakeShm *shm) {
    if (!shm || !shm->removed || shm->attached_count > 0) {
        return;
    }

    FakeShm **link = &g_fake_shm;
    while (*link) {
        if (*link == shm) {
            *link = shm->next;
            break;
        }
        link = &(*link)->next;
    }

    remove_xcb_segments_for_shm_locked(shm);
    free(shm->buffer);
    free(shm);
}

int shmget(key_t key, size_t size, int shmflg) {
    static real_shmget_fn real_shmget;
    if (!real_shmget) {
        real_shmget = (real_shmget_fn)lookup_symbol("shmget", "libc.so.6");
    }

    int rc = real_shmget ? real_shmget(key, size, shmflg) : -1;
    if (rc >= 0) {
        return rc;
    }

    int saved_errno = real_shmget ? errno : ENOSYS;
    if (saved_errno != ENOSYS || key != IPC_PRIVATE ||
        !(shmflg & IPC_CREAT) || size == 0) {
        errno = saved_errno;
        return -1;
    }

    FakeShm *item = (FakeShm *)calloc(1, sizeof(*item));
    if (!item) {
        errno = ENOMEM;
        return -1;
    }

    item->buffer = (uint8_t *)calloc(1, size);
    if (!item->buffer) {
        free(item);
        errno = ENOMEM;
        return -1;
    }

    pthread_mutex_lock(&g_lock);
    item->id = g_next_shmid++;
    item->size = size;
    item->next = g_fake_shm;
    g_fake_shm = item;
    pthread_mutex_unlock(&g_lock);

    shim_log("fake shmget key=%ld size=%zu flags=0%o -> shmid=%d", (long)key,
             size, shmflg, item->id);
    return item->id;
}

void *shmat(int shmid, const void *shmaddr, int shmflg) {
    pthread_mutex_lock(&g_lock);
    FakeShm *item = find_fake_shm_locked(shmid);
    if (item) {
        if (shmaddr) {
            pthread_mutex_unlock(&g_lock);
            errno = EINVAL;
            return (void *)-1;
        }

        item->attached_count++;
        void *buffer = item->buffer;
        pthread_mutex_unlock(&g_lock);

        shim_log("fake shmat shmid=%d flags=0%o -> %p", shmid, shmflg,
                 buffer);
        return buffer;
    }
    pthread_mutex_unlock(&g_lock);

    static real_shmat_fn real_shmat;
    if (!real_shmat) {
        real_shmat = (real_shmat_fn)lookup_symbol("shmat", "libc.so.6");
    }
    if (!real_shmat) {
        errno = ENOSYS;
        return (void *)-1;
    }
    return real_shmat(shmid, shmaddr, shmflg);
}

int shmdt(const void *shmaddr) {
    pthread_mutex_lock(&g_lock);
    FakeShm *item = find_fake_shm_by_addr_locked(shmaddr);
    if (item) {
        if (item->attached_count > 0) {
            item->attached_count--;
        }
        shim_log("fake shmdt addr=%p shmid=%d attached=%d", shmaddr, item->id,
                 item->attached_count);
        maybe_free_fake_shm_locked(item);
        pthread_mutex_unlock(&g_lock);
        return 0;
    }
    pthread_mutex_unlock(&g_lock);

    static real_shmdt_fn real_shmdt;
    if (!real_shmdt) {
        real_shmdt = (real_shmdt_fn)lookup_symbol("shmdt", "libc.so.6");
    }
    if (!real_shmdt) {
        errno = ENOSYS;
        return -1;
    }
    return real_shmdt(shmaddr);
}

int shmctl(int shmid, int cmd, struct shmid_ds *buf) {
    pthread_mutex_lock(&g_lock);
    FakeShm *item = find_fake_shm_locked(shmid);
    if (item) {
        if (cmd == IPC_RMID) {
            item->removed = 1;
            shim_log("fake shmctl IPC_RMID shmid=%d", shmid);
            maybe_free_fake_shm_locked(item);
            pthread_mutex_unlock(&g_lock);
            return 0;
        }

        if (cmd == IPC_STAT && buf) {
            memset(buf, 0, sizeof(*buf));
            buf->shm_segsz = item->size;
            pthread_mutex_unlock(&g_lock);
            return 0;
        }

        pthread_mutex_unlock(&g_lock);
        errno = EINVAL;
        return -1;
    }
    pthread_mutex_unlock(&g_lock);

    static real_shmctl_fn real_shmctl;
    if (!real_shmctl) {
        real_shmctl = (real_shmctl_fn)lookup_symbol("shmctl", "libc.so.6");
    }
    if (!real_shmctl) {
        errno = ENOSYS;
        return -1;
    }
    return real_shmctl(shmid, cmd, buf);
}

xcb_void_cookie_t xcb_shm_attach(xcb_connection_t *connection,
                                 xcb_shm_seg_t shmseg, uint32_t shmid,
                                 uint8_t read_only) {
    pthread_mutex_lock(&g_lock);
    FakeShm *shm = find_fake_shm_locked((int)shmid);
    if (shm) {
        FakeXcbSeg *seg = find_fake_xcb_locked(connection, shmseg);
        if (!seg) {
            seg = (FakeXcbSeg *)calloc(1, sizeof(*seg));
            if (seg) {
                seg->next = g_fake_xcb;
                g_fake_xcb = seg;
            }
        }

        if (seg) {
            seg->connection = connection;
            seg->xcbid = shmseg;
            seg->shm = shm;
            shim_log("fake xcb_shm_attach conn=%p shmseg=%u shmid=%u "
                     "read_only=%u",
                     (void *)connection, shmseg, shmid, read_only);
        } else {
            shim_log("fake xcb_shm_attach allocation failed shmseg=%u shmid=%u",
                     shmseg, shmid);
        }

        pthread_mutex_unlock(&g_lock);
        return (xcb_void_cookie_t){0};
    }
    pthread_mutex_unlock(&g_lock);

    static real_xcb_shm_attach_fn real_attach;
    if (!real_attach) {
        real_attach = (real_xcb_shm_attach_fn)lookup_symbol(
            "xcb_shm_attach", "libxcb-shm.so.0");
    }
    return real_attach ? real_attach(connection, shmseg, shmid, read_only)
                       : (xcb_void_cookie_t){0};
}

xcb_void_cookie_t xcb_shm_detach(xcb_connection_t *connection,
                                 xcb_shm_seg_t shmseg) {
    pthread_mutex_lock(&g_lock);
    FakeXcbSeg **link = &g_fake_xcb;
    while (*link) {
        FakeXcbSeg *item = *link;
        if (item->connection == connection && item->xcbid == shmseg) {
            *link = item->next;
            free(item);
            pthread_mutex_unlock(&g_lock);
            shim_log("fake xcb_shm_detach conn=%p shmseg=%u",
                     (void *)connection, shmseg);
            return (xcb_void_cookie_t){0};
        }
        link = &item->next;
    }
    pthread_mutex_unlock(&g_lock);

    static real_xcb_shm_detach_fn real_detach;
    if (!real_detach) {
        real_detach = (real_xcb_shm_detach_fn)lookup_symbol(
            "xcb_shm_detach", "libxcb-shm.so.0");
    }
    return real_detach ? real_detach(connection, shmseg)
                       : (xcb_void_cookie_t){0};
}

xcb_shm_get_image_cookie_t xcb_shm_get_image_unchecked(
    xcb_connection_t *connection, xcb_drawable_t drawable, int16_t x, int16_t y,
    uint16_t width, uint16_t height, uint32_t plane_mask, uint8_t format,
    xcb_shm_seg_t shmseg, uint32_t offset) {
    pthread_mutex_lock(&g_lock);
    FakeXcbSeg *seg = find_fake_xcb_locked(connection, shmseg);
    if (seg) {
        unsigned int sequence = g_next_sequence++;
        PendingImage *pending = (PendingImage *)calloc(1, sizeof(*pending));
        if (pending) {
            pending->sequence = sequence;
            pending->connection = connection;
            pending->drawable = drawable;
            pending->x = x;
            pending->y = y;
            pending->width = width;
            pending->height = height;
            pending->plane_mask = plane_mask;
            pending->format = format;
            pending->xcbid = shmseg;
            pending->offset = offset;
            pending->next = g_pending;
            g_pending = pending;
        }
        pthread_mutex_unlock(&g_lock);

        shim_log("fake xcb_shm_get_image_unchecked conn=%p drawable=%u "
                 "rect=%ux%u+%d+%d shmseg=%u offset=%u cookie=%u",
                 (void *)connection, drawable, width, height, x, y, shmseg,
                 offset, sequence);
        return (xcb_shm_get_image_cookie_t){sequence};
    }
    pthread_mutex_unlock(&g_lock);

    static real_xcb_shm_get_image_unchecked_fn real_get_image;
    if (!real_get_image) {
        real_get_image = (real_xcb_shm_get_image_unchecked_fn)lookup_symbol(
            "xcb_shm_get_image_unchecked", "libxcb-shm.so.0");
    }
    return real_get_image
               ? real_get_image(connection, drawable, x, y, width, height,
                                plane_mask, format, shmseg, offset)
               : (xcb_shm_get_image_cookie_t){0};
}

xcb_shm_get_image_reply_t *
xcb_shm_get_image_reply(xcb_connection_t *connection,
                        xcb_shm_get_image_cookie_t cookie,
                        xcb_generic_error_t **error) {
    pthread_mutex_lock(&g_lock);
    PendingImage *pending = take_pending_locked(connection, cookie.sequence);
    FakeXcbSeg *seg = pending ? find_fake_xcb_locked(connection, pending->xcbid)
                              : NULL;
    FakeShm *shm = seg ? seg->shm : NULL;
    uint8_t *buffer = shm ? shm->buffer : NULL;
    size_t buffer_size = shm ? shm->size : 0;
    pthread_mutex_unlock(&g_lock);

    if (!pending) {
        if (cookie.sequence >= 0x53480000U) {
            shim_log("missing fake request for cookie=%u", cookie.sequence);
            return NULL;
        }

        static real_xcb_shm_get_image_reply_fn real_reply;
        if (!real_reply) {
            real_reply = (real_xcb_shm_get_image_reply_fn)lookup_symbol(
                "xcb_shm_get_image_reply", "libxcb-shm.so.0");
        }
        return real_reply ? real_reply(connection, cookie, error) : NULL;
    }

    if (!buffer) {
        shim_log("fake request has no live buffer cookie=%u", cookie.sequence);
        free(pending);
        return NULL;
    }

    static real_xcb_get_image_fn real_get_image;
    static real_xcb_get_image_reply_fn real_get_image_reply;
    static real_xcb_get_image_data_fn real_get_image_data;
    static real_xcb_get_image_data_length_fn real_get_image_data_length;

    if (!real_get_image) {
        real_get_image =
            (real_xcb_get_image_fn)lookup_symbol("xcb_get_image", "libxcb.so.1");
    }
    if (!real_get_image_reply) {
        real_get_image_reply = (real_xcb_get_image_reply_fn)lookup_symbol(
            "xcb_get_image_reply", "libxcb.so.1");
    }
    if (!real_get_image_data) {
        real_get_image_data = (real_xcb_get_image_data_fn)lookup_symbol(
            "xcb_get_image_data", "libxcb.so.1");
    }
    if (!real_get_image_data_length) {
        real_get_image_data_length =
            (real_xcb_get_image_data_length_fn)lookup_symbol(
                "xcb_get_image_data_length", "libxcb.so.1");
    }

    if (!real_get_image || !real_get_image_reply || !real_get_image_data ||
        !real_get_image_data_length) {
        shim_log("xcb_get_image symbols unavailable");
        free(pending);
        return NULL;
    }

    if (error) {
        *error = NULL;
    }

    xcb_generic_error_t *local_error = NULL;
    xcb_get_image_cookie_t image_cookie = real_get_image(
        connection, pending->format, pending->drawable, pending->x, pending->y,
        pending->width, pending->height, pending->plane_mask);
    xcb_get_image_reply_t *image_reply =
        real_get_image_reply(connection, image_cookie, &local_error);

    if (local_error) {
        shim_log("xcb_get_image error code=%u", local_error->error_code);
        if (error) {
            *error = local_error;
        } else {
            free(local_error);
        }
        free(pending);
        return NULL;
    }

    if (!image_reply) {
        shim_log("xcb_get_image returned null reply");
        free(pending);
        return NULL;
    }

    uint8_t *data = real_get_image_data(image_reply);
    int data_len_i = real_get_image_data_length(image_reply);
    size_t copied = 0;

    if (data && data_len_i > 0 && pending->offset < buffer_size) {
        size_t data_len = (size_t)data_len_i;
        size_t available = buffer_size - pending->offset;
        copied = data_len < available ? data_len : available;
        memcpy(buffer + pending->offset, data, copied);
        if (copied < data_len) {
            shim_log("truncated image data from %zu to %zu bytes", data_len,
                     copied);
        }
    } else {
        shim_log("xcb_get_image empty data len=%d offset=%u buffer_size=%zu",
                 data_len_i, pending->offset, buffer_size);
    }

    xcb_shm_get_image_reply_t *reply =
        (xcb_shm_get_image_reply_t *)calloc(1, sizeof(*reply));
    if (reply) {
        reply->response_type = image_reply->response_type;
        reply->depth = image_reply->depth;
        reply->sequence = (uint16_t)(cookie.sequence & 0xffffU);
        reply->length = 0;
        reply->visual = image_reply->visual;
        reply->size = (uint32_t)copied;
    }

    shim_log("served fake xcb_shm_get_image_reply cookie=%u copied=%zu "
             "depth=%u visual=%u",
             cookie.sequence, copied, image_reply->depth, image_reply->visual);

    free(image_reply);
    free(pending);
    return reply;
}
