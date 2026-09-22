#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <unistd.h>

typedef struct xdo_stub *Xdo;
typedef void XDisplay;
typedef unsigned long XWindow;
typedef unsigned long XTime;
typedef int XBool;
typedef struct xcb_connection_t xcb_connection_t;
typedef struct xcb_setup_t xcb_setup_t;
typedef uint32_t xcb_window_t;

typedef struct {
    unsigned int sequence;
} xcb_void_cookie_t;

typedef struct {
    xcb_window_t root;
    uint32_t default_colormap;
    uint32_t white_pixel;
    uint32_t black_pixel;
    uint32_t current_input_masks;
    uint16_t width_in_pixels;
    uint16_t height_in_pixels;
    uint16_t width_in_millimeters;
    uint16_t height_in_millimeters;
    uint16_t min_installed_maps;
    uint16_t max_installed_maps;
    uint32_t root_visual;
    uint8_t backing_stores;
    uint8_t save_unders;
    uint8_t root_depth;
    uint8_t allowed_depths_len;
} xcb_screen_t;

typedef struct {
    xcb_screen_t *data;
    int rem;
    int index;
} xcb_screen_iterator_t;

#define shim_old_dlsym dlsym
#define shim_old_dlopen dlopen

typedef XDisplay *(*real_XOpenDisplay_fn)(const char *);
typedef int (*real_XCloseDisplay_fn)(XDisplay *);
typedef int (*real_XFlush_fn)(XDisplay *);
typedef int (*real_XSync_fn)(XDisplay *, int);
typedef int (*real_XTestQueryExtension_fn)(XDisplay *, int *, int *, int *,
                                           int *);
typedef int (*real_XTestFakeKeyEvent_fn)(XDisplay *, unsigned int, int,
                                         unsigned long);
typedef int (*real_XTestFakeButtonEvent_fn)(XDisplay *, unsigned int, int,
                                            unsigned long);
typedef int (*real_XTestFakeMotionEvent_fn)(XDisplay *, int, int, int,
                                            unsigned long);
typedef int (*real_XTestFakeRelativeMotionEvent_fn)(XDisplay *, int, int,
                                                    unsigned long);
typedef void *(*real_XFixesGetCursorImage_fn)(XDisplay *);
typedef int (*real_XQueryPointer_fn)(XDisplay *, XWindow, XWindow *, XWindow *,
                                     int *, int *, int *, int *,
                                     unsigned int *);
typedef XWindow (*real_XRootWindow_fn)(XDisplay *, int);

typedef Xdo (*real_xdo_new_fn)(const char *);
typedef void (*real_xdo_free_fn)(Xdo);
typedef int (*real_xdo_move_mouse_fn)(Xdo, int, int, int);
typedef int (*real_xdo_move_mouse_relative_fn)(Xdo, int, int);
typedef int (*real_xdo_mouse_down_fn)(Xdo, XWindow, int);
typedef int (*real_xdo_mouse_up_fn)(Xdo, XWindow, int);
typedef int (*real_xdo_click_window_fn)(Xdo, XWindow, int);
typedef int (*real_xdo_enter_text_window_fn)(Xdo, XWindow, const char *,
                                             unsigned int);
typedef int (*real_xdo_send_keysequence_window_fn)(Xdo, XWindow, const char *,
                                                   unsigned int);
typedef int (*real_xdo_send_keysequence_window_down_fn)(Xdo, XWindow,
                                                        const char *,
                                                        unsigned int);
typedef int (*real_xdo_send_keysequence_window_up_fn)(Xdo, XWindow,
                                                      const char *,
                                                      unsigned int);
typedef unsigned int (*real_xdo_get_input_state_fn)(Xdo);
typedef int (*real_xdo_get_mouse_location_fn)(Xdo, int *, int *, int *);
typedef int (*real_xdo_get_active_window_fn)(Xdo, XWindow *);
typedef int (*real_xdo_get_window_location_fn)(Xdo, XWindow, int *, int *,
                                               int *);
typedef int (*real_xdo_get_window_size_fn)(Xdo, XWindow, int *, int *);
typedef xcb_connection_t *(*real_xcb_connect_fn)(const char *, int *);
typedef void (*real_xcb_disconnect_fn)(xcb_connection_t *);
typedef int (*real_xcb_connection_has_error_fn)(xcb_connection_t *);
typedef const xcb_setup_t *(*real_xcb_get_setup_fn)(xcb_connection_t *);
typedef xcb_screen_iterator_t (*real_xcb_setup_roots_iterator_fn)(
    const xcb_setup_t *);
typedef void (*real_xcb_screen_next_fn)(xcb_screen_iterator_t *);
typedef xcb_void_cookie_t (*real_xcb_warp_pointer_fn)(
    xcb_connection_t *, xcb_window_t, xcb_window_t, int16_t, int16_t, uint16_t,
    uint16_t, int16_t, int16_t);
typedef int (*real_xcb_flush_fn)(xcb_connection_t *);

typedef struct {
    int fd;
    int width;
    int height;
    int x;
    int y;
    int have_mouse_pos;
    int mouse_mode;
    int mouse_rel_scale;
    unsigned int modifier_mask;
    int caps_lock;
    int num_lock;
    int initialized;
    int failed;
} UInputState;

typedef struct {
    xcb_connection_t *connection;
    xcb_window_t root;
    int width;
    int height;
    int initialized;
    int failed;
} XcbMouseState;

static pthread_mutex_t g_input_lock = PTHREAD_MUTEX_INITIALIZER;
static UInputState g_input = {
    .fd = -1,
    .width = 1024,
    .height = 600,
};
static XcbMouseState g_xcb_mouse;
static int g_fake_display_token;
static int g_fake_xdo_token;

static real_xcb_connect_fn p_xcb_connect;
static real_xcb_disconnect_fn p_xcb_disconnect;
static real_xcb_connection_has_error_fn p_xcb_connection_has_error;
static real_xcb_get_setup_fn p_xcb_get_setup;
static real_xcb_setup_roots_iterator_fn p_xcb_setup_roots_iterator;
static real_xcb_screen_next_fn p_xcb_screen_next;
static real_xcb_warp_pointer_fn p_xcb_warp_pointer;
static real_xcb_flush_fn p_xcb_flush;

static void *input_lookup_symbol(const char *name, const char *fallback) {
    void *symbol = shim_old_dlsym(RTLD_NEXT, name);
    if (!symbol && fallback) {
        void *handle = shim_old_dlopen(fallback, RTLD_LAZY | RTLD_GLOBAL);
        if (handle) {
            symbol = shim_old_dlsym(handle, name);
        }
    }
    return symbol;
}

static int input_fallback_enabled(void) {
    static int checked;
    static int enabled;

    if (!checked) {
        const char *env = getenv("RUSTDESK_UINPUT_INPUT_FALLBACK");
        int requested = env && env[0] && strcmp(env, "0") != 0;
        int forced = 0;
        const char *force_env = getenv("RUSTDESK_UINPUT_INPUT_FORCE");
        forced = force_env && force_env[0] && strcmp(force_env, "0") != 0;

        enabled = 0;
        if (requested) {
            if (forced) {
                enabled = 1;
            } else {
                FILE *cmdline = fopen("/proc/self/cmdline", "rb");
                if (cmdline) {
                    char buf[4096];
                    size_t n = fread(buf, 1, sizeof(buf) - 1, cmdline);
                    fclose(cmdline);
                    buf[n] = '\0';
                    for (size_t i = 0; i < n;) {
                        char *arg = &buf[i];
                        size_t len = strlen(arg);
                        if (strcmp(arg, "--server") == 0) {
                            enabled = 1;
                            break;
                        }
                        i += len + 1;
                    }
                }
            }
        }
        checked = 1;
    }
    return enabled;
}

static int input_log_enabled(void) {
    static int checked;
    static int enabled;

    if (!checked) {
        const char *env = getenv("RUSTDESK_UINPUT_INPUT_LOG");
        enabled = env && env[0] && strcmp(env, "0") != 0;
        checked = 1;
    }
    return enabled;
}

static int xcb_mouse_fallback_enabled(void) {
    static int checked;
    static int enabled;

    if (!checked) {
        const char *env = getenv("RUSTDESK_XCB_MOUSE_FALLBACK");
        enabled = env ? (env[0] && strcmp(env, "0") != 0)
                      : input_fallback_enabled();
        checked = 1;
    }
    return enabled;
}

static void input_log(const char *fmt, ...) {
    if (!input_log_enabled()) {
        return;
    }

    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[rustdesk-uinput-input-fallback] ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
}

static int is_fake_display(const void *display) {
    return display == (const void *)&g_fake_display_token;
}

static int is_fake_xdo(Xdo xdo) {
    return xdo == (Xdo)&g_fake_xdo_token;
}

static int env_int(const char *name, int fallback) {
    const char *value = getenv(name);
    if (!value || !value[0]) {
        return fallback;
    }

    char *end = NULL;
    long parsed = strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > 100000) {
        return fallback;
    }
    return (int)parsed;
}

static int load_xcb_mouse_symbols_locked(void) {
    if (p_xcb_connect && p_xcb_disconnect && p_xcb_connection_has_error &&
        p_xcb_get_setup && p_xcb_setup_roots_iterator && p_xcb_screen_next &&
        p_xcb_warp_pointer && p_xcb_flush) {
        return 1;
    }

    p_xcb_connect =
        (real_xcb_connect_fn)input_lookup_symbol("xcb_connect", "libxcb.so.1");
    p_xcb_disconnect = (real_xcb_disconnect_fn)input_lookup_symbol(
        "xcb_disconnect", "libxcb.so.1");
    p_xcb_connection_has_error =
        (real_xcb_connection_has_error_fn)input_lookup_symbol(
            "xcb_connection_has_error", "libxcb.so.1");
    p_xcb_get_setup = (real_xcb_get_setup_fn)input_lookup_symbol(
        "xcb_get_setup", "libxcb.so.1");
    p_xcb_setup_roots_iterator =
        (real_xcb_setup_roots_iterator_fn)input_lookup_symbol(
            "xcb_setup_roots_iterator", "libxcb.so.1");
    p_xcb_screen_next = (real_xcb_screen_next_fn)input_lookup_symbol(
        "xcb_screen_next", "libxcb.so.1");
    p_xcb_warp_pointer = (real_xcb_warp_pointer_fn)input_lookup_symbol(
        "xcb_warp_pointer", "libxcb.so.1");
    p_xcb_flush =
        (real_xcb_flush_fn)input_lookup_symbol("xcb_flush", "libxcb.so.1");

    return p_xcb_connect && p_xcb_disconnect && p_xcb_connection_has_error &&
           p_xcb_get_setup && p_xcb_setup_roots_iterator && p_xcb_screen_next &&
           p_xcb_warp_pointer && p_xcb_flush;
}

static int xcb_mouse_init_locked(void) {
    if (!xcb_mouse_fallback_enabled()) {
        return 0;
    }
    if (g_xcb_mouse.initialized) {
        return g_xcb_mouse.connection != NULL;
    }
    if (g_xcb_mouse.failed) {
        return 0;
    }

    if (!load_xcb_mouse_symbols_locked()) {
        input_log("xcb mouse symbols unavailable");
        g_xcb_mouse.failed = 1;
        return 0;
    }

    int screen_num = 0;
    const char *display = getenv("DISPLAY");
    if (!display || !display[0]) {
        display = ":0";
    }

    xcb_connection_t *connection = p_xcb_connect(display, &screen_num);
    if (!connection || p_xcb_connection_has_error(connection)) {
        input_log("xcb_connect(%s) failed", display);
        if (connection) {
            p_xcb_disconnect(connection);
        }
        g_xcb_mouse.failed = 1;
        return 0;
    }

    const xcb_setup_t *setup = p_xcb_get_setup(connection);
    xcb_screen_iterator_t iter = p_xcb_setup_roots_iterator(setup);
    for (int i = 0; i < screen_num && iter.rem > 0; ++i) {
        p_xcb_screen_next(&iter);
    }
    if (!iter.data) {
        input_log("xcb has no screen data for screen=%d", screen_num);
        p_xcb_disconnect(connection);
        g_xcb_mouse.failed = 1;
        return 0;
    }

    g_xcb_mouse.connection = connection;
    g_xcb_mouse.root = iter.data->root;
    g_xcb_mouse.width = iter.data->width_in_pixels;
    g_xcb_mouse.height = iter.data->height_in_pixels;
    g_xcb_mouse.initialized = 1;
    if (g_xcb_mouse.width > 0) {
        g_input.width = g_xcb_mouse.width;
    }
    if (g_xcb_mouse.height > 0) {
        g_input.height = g_xcb_mouse.height;
    }
    input_log("xcb mouse ready display=%s root=%u size=%dx%d", display,
              g_xcb_mouse.root, g_xcb_mouse.width, g_xcb_mouse.height);
    return 1;
}

static int mouse_mode_from_env(void) {
    const char *value = getenv("RUSTDESK_UINPUT_MOUSE_MODE");
    if (!value || !value[0] || strcmp(value, "anchor") == 0) {
        return 1;
    }
    if (strcmp(value, "relative") == 0) {
        return 0;
    }
    if (strcmp(value, "abs") == 0 || strcmp(value, "absolute") == 0) {
        return 2;
    }
    return 1;
}

static void load_input_geometry_locked(void) {
    g_input.width = env_int("RUSTDESK_UINPUT_WIDTH", g_input.width);
    g_input.height = env_int("RUSTDESK_UINPUT_HEIGHT", g_input.height);
    g_input.mouse_mode = mouse_mode_from_env();
    g_input.mouse_rel_scale =
        env_int("RUSTDESK_UINPUT_MOUSE_REL_SCALE", g_input.mouse_rel_scale);
    if (g_input.width < 1) {
        g_input.width = 1024;
    }
    if (g_input.height < 1) {
        g_input.height = 600;
    }
    if (g_input.mouse_rel_scale < 1) {
        g_input.mouse_rel_scale = 2;
    }
}

static int setup_abs_axis(int fd, unsigned int code, int min, int max) {
    struct uinput_abs_setup abs_setup;
    memset(&abs_setup, 0, sizeof(abs_setup));
    abs_setup.code = code;
    abs_setup.absinfo.minimum = min;
    abs_setup.absinfo.maximum = max;
    return ioctl(fd, UI_ABS_SETUP, &abs_setup);
}

static int setup_uinput_modern_locked(int fd) {
    struct uinput_setup setup;
    memset(&setup, 0, sizeof(setup));
    setup.id.bustype = BUS_USB;
    setup.id.vendor = 0x5255;
    setup.id.product = 0x494e;
    setup.id.version = 1;
    snprintf(setup.name, sizeof(setup.name), "RustDesk uinput fallback");
    if (ioctl(fd, UI_DEV_SETUP, &setup) < 0) {
        return -1;
    }
    return ioctl(fd, UI_DEV_CREATE);
}

static int setup_uinput_legacy_locked(int fd) {
    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof(dev));
    snprintf(dev.name, sizeof(dev.name), "RustDesk uinput fallback");
    dev.id.bustype = BUS_USB;
    dev.id.vendor = 0x5255;
    dev.id.product = 0x494e;
    dev.id.version = 1;
    dev.absmin[ABS_X] = 0;
    dev.absmax[ABS_X] = g_input.width - 1;
    dev.absmin[ABS_Y] = 0;
    dev.absmax[ABS_Y] = g_input.height - 1;
    if (write(fd, &dev, sizeof(dev)) != (ssize_t)sizeof(dev)) {
        return -1;
    }
    return ioctl(fd, UI_DEV_CREATE);
}

static void set_all_keyboard_bits(int fd) {
    for (int key = KEY_ESC; key <= KEY_MICMUTE; ++key) {
        ioctl(fd, UI_SET_KEYBIT, key);
    }
}

static int uinput_init_locked(void) {
    if (g_input.initialized) {
        return g_input.fd >= 0;
    }
    if (g_input.failed) {
        return 0;
    }

    load_input_geometry_locked();

    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        input_log("open /dev/uinput failed: %s", strerror(errno));
        g_input.failed = 1;
        return 0;
    }

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    set_all_keyboard_bits(fd);
    ioctl(fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT);
    ioctl(fd, UI_SET_KEYBIT, BTN_MIDDLE);
    ioctl(fd, UI_SET_KEYBIT, BTN_BACK);
    ioctl(fd, UI_SET_KEYBIT, BTN_FORWARD);

    ioctl(fd, UI_SET_EVBIT, EV_REL);
    ioctl(fd, UI_SET_RELBIT, REL_X);
    ioctl(fd, UI_SET_RELBIT, REL_Y);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
    ioctl(fd, UI_SET_RELBIT, REL_HWHEEL);

    if (g_input.mouse_mode == 2) {
        ioctl(fd, UI_SET_EVBIT, EV_ABS);
        ioctl(fd, UI_SET_ABSBIT, ABS_X);
        ioctl(fd, UI_SET_ABSBIT, ABS_Y);
        setup_abs_axis(fd, ABS_X, 0, g_input.width - 1);
        setup_abs_axis(fd, ABS_Y, 0, g_input.height - 1);
    }

    if (setup_uinput_modern_locked(fd) < 0) {
        int saved = errno;
        input_log("UI_DEV_SETUP path failed: %s; trying legacy uinput setup",
                  strerror(saved));
        if (setup_uinput_legacy_locked(fd) < 0) {
            input_log("UI_DEV_CREATE failed: %s", strerror(errno));
            close(fd);
            g_input.failed = 1;
            return 0;
        }
    }

    usleep(300000);
    g_input.fd = fd;
    g_input.x = g_input.width / 2;
    g_input.y = g_input.height / 2;
    g_input.have_mouse_pos = 0;
    g_input.initialized = 1;
    input_log("uinput device ready width=%d height=%d mouse_mode=%d "
              "mouse_rel_scale=%d",
              g_input.width, g_input.height, g_input.mouse_mode,
              g_input.mouse_rel_scale);
    return 1;
}

static int emit_event_locked(int type, int code, int value) {
    if (!uinput_init_locked()) {
        return -1;
    }

    struct input_event event;
    memset(&event, 0, sizeof(event));
    gettimeofday(&event.time, NULL);
    event.type = (uint16_t)type;
    event.code = (uint16_t)code;
    event.value = value;

    ssize_t written = write(g_input.fd, &event, sizeof(event));
    return written == (ssize_t)sizeof(event) ? 0 : -1;
}

static int sync_events_locked(void) {
    int rc = emit_event_locked(EV_SYN, SYN_REPORT, 0);
    usleep(1000);
    return rc;
}

static void update_modifier_state_locked(int key, int down) {
    const unsigned int shift = 1U << 0;
    const unsigned int lock = 1U << 1;
    const unsigned int control = 1U << 2;
    const unsigned int alt = 1U << 3;
    const unsigned int numlock = 1U << 4;
    const unsigned int meta = 1U << 6;
    unsigned int bit = 0;

    switch (key) {
    case KEY_LEFTSHIFT:
    case KEY_RIGHTSHIFT:
        bit = shift;
        break;
    case KEY_LEFTCTRL:
    case KEY_RIGHTCTRL:
        bit = control;
        break;
    case KEY_LEFTALT:
    case KEY_RIGHTALT:
        bit = alt;
        break;
    case KEY_LEFTMETA:
    case KEY_RIGHTMETA:
        bit = meta;
        break;
    case KEY_CAPSLOCK:
        if (down) {
            g_input.caps_lock = !g_input.caps_lock;
            if (g_input.caps_lock) {
                g_input.modifier_mask |= lock;
            } else {
                g_input.modifier_mask &= ~lock;
            }
        }
        return;
    case KEY_NUMLOCK:
        if (down) {
            g_input.num_lock = !g_input.num_lock;
            if (g_input.num_lock) {
                g_input.modifier_mask |= numlock;
            } else {
                g_input.modifier_mask &= ~numlock;
            }
        }
        return;
    default:
        return;
    }

    if (down) {
        g_input.modifier_mask |= bit;
    } else {
        g_input.modifier_mask &= ~bit;
    }
}

static int key_event_locked(int key, int down) {
    if (key <= 0) {
        return 0;
    }
    update_modifier_state_locked(key, down);
    emit_event_locked(EV_KEY, key, down ? 1 : 0);
    return sync_events_locked();
}

static int key_click_locked(int key) {
    key_event_locked(key, 1);
    return key_event_locked(key, 0);
}

static int char_to_key(char ch, int *key, int *shift) {
    *shift = 0;
    if (ch >= 'a' && ch <= 'z') {
        *key = KEY_A + (ch - 'a');
        return 1;
    }
    if (ch >= 'A' && ch <= 'Z') {
        *key = KEY_A + (ch - 'A');
        *shift = 1;
        return 1;
    }
    if (ch >= '1' && ch <= '9') {
        *key = KEY_1 + (ch - '1');
        return 1;
    }
    if (ch == '0') {
        *key = KEY_0;
        return 1;
    }

    switch (ch) {
    case ' ':
        *key = KEY_SPACE;
        return 1;
    case '\n':
    case '\r':
        *key = KEY_ENTER;
        return 1;
    case '\t':
        *key = KEY_TAB;
        return 1;
    case '!':
        *key = KEY_1;
        *shift = 1;
        return 1;
    case '@':
        *key = KEY_2;
        *shift = 1;
        return 1;
    case '#':
        *key = KEY_3;
        *shift = 1;
        return 1;
    case '$':
        *key = KEY_4;
        *shift = 1;
        return 1;
    case '%':
        *key = KEY_5;
        *shift = 1;
        return 1;
    case '^':
        *key = KEY_6;
        *shift = 1;
        return 1;
    case '&':
        *key = KEY_7;
        *shift = 1;
        return 1;
    case '*':
        *key = KEY_8;
        *shift = 1;
        return 1;
    case '(':
        *key = KEY_9;
        *shift = 1;
        return 1;
    case ')':
        *key = KEY_0;
        *shift = 1;
        return 1;
    case '-':
        *key = KEY_MINUS;
        return 1;
    case '_':
        *key = KEY_MINUS;
        *shift = 1;
        return 1;
    case '=':
        *key = KEY_EQUAL;
        return 1;
    case '+':
        *key = KEY_EQUAL;
        *shift = 1;
        return 1;
    case '[':
        *key = KEY_LEFTBRACE;
        return 1;
    case '{':
        *key = KEY_LEFTBRACE;
        *shift = 1;
        return 1;
    case ']':
        *key = KEY_RIGHTBRACE;
        return 1;
    case '}':
        *key = KEY_RIGHTBRACE;
        *shift = 1;
        return 1;
    case '\\':
        *key = KEY_BACKSLASH;
        return 1;
    case '|':
        *key = KEY_BACKSLASH;
        *shift = 1;
        return 1;
    case ';':
        *key = KEY_SEMICOLON;
        return 1;
    case ':':
        *key = KEY_SEMICOLON;
        *shift = 1;
        return 1;
    case '\'':
        *key = KEY_APOSTROPHE;
        return 1;
    case '"':
        *key = KEY_APOSTROPHE;
        *shift = 1;
        return 1;
    case '`':
        *key = KEY_GRAVE;
        return 1;
    case '~':
        *key = KEY_GRAVE;
        *shift = 1;
        return 1;
    case ',':
        *key = KEY_COMMA;
        return 1;
    case '<':
        *key = KEY_COMMA;
        *shift = 1;
        return 1;
    case '.':
        *key = KEY_DOT;
        return 1;
    case '>':
        *key = KEY_DOT;
        *shift = 1;
        return 1;
    case '/':
        *key = KEY_SLASH;
        return 1;
    case '?':
        *key = KEY_SLASH;
        *shift = 1;
        return 1;
    default:
        return 0;
    }
}

static int type_char_locked(char ch) {
    int key = 0;
    int shift = 0;
    if (!char_to_key(ch, &key, &shift)) {
        return 0;
    }
    if (shift) {
        key_event_locked(KEY_LEFTSHIFT, 1);
    }
    key_click_locked(key);
    if (shift) {
        key_event_locked(KEY_LEFTSHIFT, 0);
    }
    return 0;
}

static int type_text_locked(const char *text) {
    if (!text) {
        return 0;
    }
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        type_char_locked((char)*p);
    }
    return 0;
}

static int parse_u_hex(const char *text, int *key, int *shift) {
    if (!text || (text[0] != 'U' && text[0] != 'u') || !text[1]) {
        return 0;
    }
    char *end = NULL;
    unsigned long value = strtoul(text + 1, &end, 16);
    if (!end || *end != '\0' || value > 0x7f) {
        return 0;
    }
    return char_to_key((char)value, key, shift);
}

static int parse_decimal_keycode(const char *text, int *key) {
    if (!text || !text[0]) {
        return 0;
    }
    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9') {
            return 0;
        }
    }
    long value = strtol(text, NULL, 10);
    if (value >= 8 && value <= KEY_MAX + 8) {
        *key = (int)value - 8;
        return 1;
    }
    if (value > 0 && value <= KEY_MAX) {
        *key = (int)value;
        return 1;
    }
    return 0;
}

static int key_from_name(const char *name, int *shift) {
    *shift = 0;
    if (!name || !name[0]) {
        return 0;
    }

    int key = 0;
    if (parse_u_hex(name, &key, shift)) {
        return key;
    }
    if (parse_decimal_keycode(name, &key)) {
        return key;
    }
    if (strlen(name) == 1 && char_to_key(name[0], &key, shift)) {
        return key;
    }

    struct NameKey {
        const char *name;
        int key;
    };
    static const struct NameKey names[] = {
        {"Alt", KEY_LEFTALT},       {"Alt_R", KEY_RIGHTALT},
        {"BackSpace", KEY_BACKSPACE},
        {"Caps_Lock", KEY_CAPSLOCK},
        {"Control", KEY_LEFTCTRL}, {"Control_L", KEY_LEFTCTRL},
        {"Control_R", KEY_RIGHTCTRL},
        {"Delete", KEY_DELETE},    {"Down", KEY_DOWN},
        {"End", KEY_END},          {"Escape", KEY_ESC},
        {"F1", KEY_F1},            {"F2", KEY_F2},
        {"F3", KEY_F3},            {"F4", KEY_F4},
        {"F5", KEY_F5},            {"F6", KEY_F6},
        {"F7", KEY_F7},            {"F8", KEY_F8},
        {"F9", KEY_F9},            {"F10", KEY_F10},
        {"F11", KEY_F11},          {"F12", KEY_F12},
        {"Home", KEY_HOME},        {"Insert", KEY_INSERT},
        {"Left", KEY_LEFT},        {"Menu", KEY_COMPOSE},
        {"Num_Lock", KEY_NUMLOCK}, {"Page_Down", KEY_PAGEDOWN},
        {"Page_Up", KEY_PAGEUP},   {"Return", KEY_ENTER},
        {"Right", KEY_RIGHT},      {"Shift", KEY_LEFTSHIFT},
        {"Shift_L", KEY_LEFTSHIFT}, {"Shift_R", KEY_RIGHTSHIFT},
        {"Super", KEY_LEFTMETA},   {"Super_R", KEY_RIGHTMETA},
        {"Tab", KEY_TAB},          {"Up", KEY_UP},
        {"space", KEY_SPACE},      {"KP_Enter", KEY_KPENTER},
        {"KP_Add", KEY_KPPLUS},    {"KP_Subtract", KEY_KPMINUS},
        {"KP_Multiply", KEY_KPASTERISK},
        {"KP_Divide", KEY_KPSLASH}, {"KP_Equal", KEY_KPEQUAL},
        {"KP_Decimal", KEY_KPDOT}, {"3270_PrintScreen", KEY_SYSRQ},
        {"Print", KEY_SYSRQ},      {"Scroll_Lock", KEY_SCROLLLOCK},
        {"Pause", KEY_PAUSE},      {NULL, 0},
    };

    for (int i = 0; names[i].name; ++i) {
        if (strcmp(name, names[i].name) == 0) {
            return names[i].key;
        }
    }
    return 0;
}

static int send_key_name_locked(const char *name, int down, int up) {
    char token[128];
    const char *start = name;
    while (start && *start) {
        const char *plus = strchr(start, '+');
        size_t len = plus ? (size_t)(plus - start) : strlen(start);
        if (len >= sizeof(token)) {
            len = sizeof(token) - 1;
        }
        memcpy(token, start, len);
        token[len] = '\0';

        int shift = 0;
        int key = key_from_name(token, &shift);
        if (key > 0) {
            if (shift && down) {
                key_event_locked(KEY_LEFTSHIFT, 1);
            }
            if (down) {
                key_event_locked(key, 1);
            }
            if (up) {
                key_event_locked(key, 0);
            }
            if (shift && up) {
                key_event_locked(KEY_LEFTSHIFT, 0);
            }
        }

        if (!plus) {
            break;
        }
        start = plus + 1;
    }
    return 0;
}

static int mouse_button_code(int button) {
    switch (button) {
    case 1:
        return BTN_LEFT;
    case 2:
        return BTN_MIDDLE;
    case 3:
        return BTN_RIGHT;
    case 8:
        return BTN_BACK;
    case 9:
        return BTN_FORWARD;
    default:
        return 0;
    }
}

static int mouse_button_locked(int button, int down) {
    if (button == 4 || button == 5 || button == 6 || button == 7) {
        int code = (button == 6 || button == 7) ? REL_HWHEEL : REL_WHEEL;
        int value = (button == 4 || button == 6) ? 1 : -1;
        emit_event_locked(EV_REL, code, value);
        return sync_events_locked();
    }

    int code = mouse_button_code(button);
    if (!code) {
        return 0;
    }
    emit_event_locked(EV_KEY, code, down ? 1 : 0);
    return sync_events_locked();
}

static int emit_relative_move_locked(int dx, int dy) {
    int scale = g_input.mouse_rel_scale > 0 ? g_input.mouse_rel_scale : 2;
    int ux = dx / scale;
    int uy = dy / scale;

    if (dx != 0 && ux == 0) {
        ux = dx > 0 ? 1 : -1;
    }
    if (dy != 0 && uy == 0) {
        uy = dy > 0 ? 1 : -1;
    }

    emit_event_locked(EV_REL, REL_X, ux);
    emit_event_locked(EV_REL, REL_Y, uy);
    return sync_events_locked();
}

static void clamp_mouse_target_locked(int *x, int *y) {
    load_input_geometry_locked();
    if (g_xcb_mouse.initialized && g_xcb_mouse.width > 0 &&
        g_xcb_mouse.height > 0) {
        g_input.width = g_xcb_mouse.width;
        g_input.height = g_xcb_mouse.height;
    }
    if (*x < 0) {
        *x = 0;
    }
    if (*y < 0) {
        *y = 0;
    }
    if (*x >= g_input.width) {
        *x = g_input.width - 1;
    }
    if (*y >= g_input.height) {
        *y = g_input.height - 1;
    }
}

static int xcb_mouse_move_to_locked(int x, int y) {
    if (!xcb_mouse_init_locked()) {
        return -1;
    }

    clamp_mouse_target_locked(&x, &y);
    p_xcb_warp_pointer(g_xcb_mouse.connection, 0, g_xcb_mouse.root, 0, 0, 0, 0,
                       (int16_t)x, (int16_t)y);
    p_xcb_flush(g_xcb_mouse.connection);
    g_input.x = x;
    g_input.y = y;
    g_input.have_mouse_pos = 1;
    return 0;
}

static int mouse_move_to_locked(int x, int y) {
    if (xcb_mouse_move_to_locked(x, y) == 0) {
        return 0;
    }

    clamp_mouse_target_locked(&x, &y);

    if (g_input.mouse_mode == 2) {
        g_input.x = x;
        g_input.y = y;
        g_input.have_mouse_pos = 1;
        emit_event_locked(EV_ABS, ABS_X, x);
        emit_event_locked(EV_ABS, ABS_Y, y);
        return sync_events_locked();
    }

    if (g_input.mouse_mode == 1 && !g_input.have_mouse_pos) {
        emit_relative_move_locked(-g_input.width * 2, -g_input.height * 2);
        g_input.x = 0;
        g_input.y = 0;
        g_input.have_mouse_pos = 1;
        input_log("anchored mouse to top-left before first move");
    } else if (!g_input.have_mouse_pos) {
        g_input.x = x;
        g_input.y = y;
        g_input.have_mouse_pos = 1;
        input_log("initialized virtual mouse position to %d,%d", x, y);
        return 0;
    }

    int dx = x - g_input.x;
    int dy = y - g_input.y;
    g_input.x = x;
    g_input.y = y;
    if (dx == 0 && dy == 0) {
        return 0;
    }
    return emit_relative_move_locked(dx, dy);
}

static int mouse_move_relative_locked(int dx, int dy) {
    load_input_geometry_locked();
    g_input.x += dx;
    g_input.y += dy;
    if (g_input.x < 0) {
        g_input.x = 0;
    }
    if (g_input.y < 0) {
        g_input.y = 0;
    }
    if (g_input.x >= g_input.width) {
        g_input.x = g_input.width - 1;
    }
    if (g_input.y >= g_input.height) {
        g_input.y = g_input.height - 1;
    }
    g_input.have_mouse_pos = 1;
    return emit_relative_move_locked(dx, dy);
}

XDisplay *XOpenDisplay(const char *display_name) {
    if (input_fallback_enabled()) {
        input_log("fake XOpenDisplay(%s)", display_name ? display_name : "");
        return (XDisplay *)&g_fake_display_token;
    }

    static real_XOpenDisplay_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XOpenDisplay_fn)input_lookup_symbol("XOpenDisplay",
                                                            "libX11.so.6");
    }
    return real_fn ? real_fn(display_name) : NULL;
}

int XCloseDisplay(XDisplay *display) {
    if (is_fake_display(display)) {
        return 0;
    }
    static real_XCloseDisplay_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XCloseDisplay_fn)input_lookup_symbol("XCloseDisplay",
                                                             "libX11.so.6");
    }
    return real_fn ? real_fn(display) : 0;
}

int XFlush(XDisplay *display) {
    if (is_fake_display(display)) {
        return 0;
    }
    static real_XFlush_fn real_fn;
    if (!real_fn) {
        real_fn =
            (real_XFlush_fn)input_lookup_symbol("XFlush", "libX11.so.6");
    }
    return real_fn ? real_fn(display) : 0;
}

int XSync(XDisplay *display, int discard) {
    if (is_fake_display(display)) {
        return 0;
    }
    static real_XSync_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XSync_fn)input_lookup_symbol("XSync", "libX11.so.6");
    }
    return real_fn ? real_fn(display, discard) : 0;
}

int XTestQueryExtension(XDisplay *display, int *event_base, int *error_base,
                        int *major_version, int *minor_version) {
    if (is_fake_display(display)) {
        if (event_base) {
            *event_base = 0;
        }
        if (error_base) {
            *error_base = 0;
        }
        if (major_version) {
            *major_version = 0;
        }
        if (minor_version) {
            *minor_version = 0;
        }
        return 0;
    }
    static real_XTestQueryExtension_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XTestQueryExtension_fn)input_lookup_symbol(
            "XTestQueryExtension", "libXtst.so.6");
    }
    return real_fn ? real_fn(display, event_base, error_base, major_version,
                             minor_version)
                   : 0;
}

int XTestFakeKeyEvent(XDisplay *display, unsigned int keycode, int is_press,
                      unsigned long delay) {
    if (is_fake_display(display)) {
        (void)delay;
        int key = keycode >= 8 ? (int)keycode - 8 : (int)keycode;
        pthread_mutex_lock(&g_input_lock);
        key_event_locked(key, is_press != 0);
        pthread_mutex_unlock(&g_input_lock);
        return 1;
    }
    static real_XTestFakeKeyEvent_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XTestFakeKeyEvent_fn)input_lookup_symbol(
            "XTestFakeKeyEvent", "libXtst.so.6");
    }
    return real_fn ? real_fn(display, keycode, is_press, delay) : 0;
}

int XTestFakeButtonEvent(XDisplay *display, unsigned int button, int is_press,
                         unsigned long delay) {
    if (is_fake_display(display)) {
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        mouse_button_locked((int)button, is_press != 0);
        pthread_mutex_unlock(&g_input_lock);
        return 1;
    }
    static real_XTestFakeButtonEvent_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XTestFakeButtonEvent_fn)input_lookup_symbol(
            "XTestFakeButtonEvent", "libXtst.so.6");
    }
    return real_fn ? real_fn(display, button, is_press, delay) : 0;
}

int XTestFakeMotionEvent(XDisplay *display, int screen, int x, int y,
                         unsigned long delay) {
    if (is_fake_display(display)) {
        (void)screen;
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        mouse_move_to_locked(x, y);
        pthread_mutex_unlock(&g_input_lock);
        return 1;
    }
    static real_XTestFakeMotionEvent_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XTestFakeMotionEvent_fn)input_lookup_symbol(
            "XTestFakeMotionEvent", "libXtst.so.6");
    }
    return real_fn ? real_fn(display, screen, x, y, delay) : 0;
}

int XTestFakeRelativeMotionEvent(XDisplay *display, int x, int y,
                                 unsigned long delay) {
    if (is_fake_display(display)) {
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        mouse_move_relative_locked(x, y);
        pthread_mutex_unlock(&g_input_lock);
        return 1;
    }
    static real_XTestFakeRelativeMotionEvent_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XTestFakeRelativeMotionEvent_fn)input_lookup_symbol(
            "XTestFakeRelativeMotionEvent", "libXtst.so.6");
    }
    return real_fn ? real_fn(display, x, y, delay) : 0;
}

void *XFixesGetCursorImage(XDisplay *display) {
    if (is_fake_display(display)) {
        return NULL;
    }
    static real_XFixesGetCursorImage_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XFixesGetCursorImage_fn)input_lookup_symbol(
            "XFixesGetCursorImage", "libXfixes.so.3");
    }
    return real_fn ? real_fn(display) : NULL;
}

int XQueryPointer(XDisplay *display, XWindow window, XWindow *root_return,
                  XWindow *child_return, int *root_x_return,
                  int *root_y_return, int *win_x_return, int *win_y_return,
                  unsigned int *mask_return) {
    if (is_fake_display(display)) {
        (void)window;
        pthread_mutex_lock(&g_input_lock);
        int x = g_input.x;
        int y = g_input.y;
        unsigned int mask = g_input.modifier_mask;
        pthread_mutex_unlock(&g_input_lock);
        if (root_return) {
            *root_return = 0;
        }
        if (child_return) {
            *child_return = 0;
        }
        if (root_x_return) {
            *root_x_return = x;
        }
        if (root_y_return) {
            *root_y_return = y;
        }
        if (win_x_return) {
            *win_x_return = x;
        }
        if (win_y_return) {
            *win_y_return = y;
        }
        if (mask_return) {
            *mask_return = mask;
        }
        return 1;
    }
    static real_XQueryPointer_fn real_fn;
    if (!real_fn) {
        real_fn = (real_XQueryPointer_fn)input_lookup_symbol("XQueryPointer",
                                                             "libX11.so.6");
    }
    return real_fn ? real_fn(display, window, root_return, child_return,
                             root_x_return, root_y_return, win_x_return,
                             win_y_return, mask_return)
                   : 0;
}

XWindow XRootWindow(XDisplay *display, int screen_number) {
    if (is_fake_display(display)) {
        (void)screen_number;
        return 0;
    }
    static real_XRootWindow_fn real_fn;
    if (!real_fn) {
        real_fn =
            (real_XRootWindow_fn)input_lookup_symbol("XRootWindow", "libX11.so.6");
    }
    return real_fn ? real_fn(display, screen_number) : 0;
}

Xdo xdo_new(const char *display) {
    if (input_fallback_enabled()) {
        input_log("fake xdo_new(%s)", display ? display : "");
        return (Xdo)&g_fake_xdo_token;
    }

    static real_xdo_new_fn real_fn;
    if (!real_fn) {
        real_fn =
            (real_xdo_new_fn)input_lookup_symbol("xdo_new", "libxdo.so.3");
    }
    return real_fn ? real_fn(display) : NULL;
}

void xdo_free(Xdo xdo) {
    if (is_fake_xdo(xdo)) {
        return;
    }
    static real_xdo_free_fn real_fn;
    if (!real_fn) {
        real_fn =
            (real_xdo_free_fn)input_lookup_symbol("xdo_free", "libxdo.so.3");
    }
    if (real_fn) {
        real_fn(xdo);
    }
}

int xdo_move_mouse(Xdo xdo, int x, int y, int screen) {
    if (is_fake_xdo(xdo)) {
        (void)screen;
        pthread_mutex_lock(&g_input_lock);
        mouse_move_to_locked(x, y);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_move_mouse_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_move_mouse_fn)input_lookup_symbol(
            "xdo_move_mouse", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, x, y, screen) : -1;
}

int xdo_move_mouse_relative(Xdo xdo, int x, int y) {
    if (is_fake_xdo(xdo)) {
        pthread_mutex_lock(&g_input_lock);
        mouse_move_relative_locked(x, y);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_move_mouse_relative_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_move_mouse_relative_fn)input_lookup_symbol(
            "xdo_move_mouse_relative", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, x, y) : -1;
}

int xdo_mouse_down(Xdo xdo, XWindow window, int button) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        pthread_mutex_lock(&g_input_lock);
        mouse_button_locked(button, 1);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_mouse_down_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_mouse_down_fn)input_lookup_symbol(
            "xdo_mouse_down", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, button) : -1;
}

int xdo_mouse_up(Xdo xdo, XWindow window, int button) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        pthread_mutex_lock(&g_input_lock);
        mouse_button_locked(button, 0);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_mouse_up_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_mouse_up_fn)input_lookup_symbol("xdo_mouse_up",
                                                            "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, button) : -1;
}

int xdo_click_window(Xdo xdo, XWindow window, int button) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        pthread_mutex_lock(&g_input_lock);
        mouse_button_locked(button, 1);
        mouse_button_locked(button, 0);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_click_window_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_click_window_fn)input_lookup_symbol(
            "xdo_click_window", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, button) : -1;
}

int xdo_enter_text_window(Xdo xdo, XWindow window, const char *string,
                          unsigned int delay) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        type_text_locked(string);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_enter_text_window_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_enter_text_window_fn)input_lookup_symbol(
            "xdo_enter_text_window", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, string, delay) : -1;
}

int xdo_send_keysequence_window(Xdo xdo, XWindow window, const char *string,
                                unsigned int delay) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        send_key_name_locked(string, 1, 1);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_send_keysequence_window_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_send_keysequence_window_fn)input_lookup_symbol(
            "xdo_send_keysequence_window", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, string, delay) : -1;
}

int xdo_send_keysequence_window_down(Xdo xdo, XWindow window,
                                     const char *string, unsigned int delay) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        send_key_name_locked(string, 1, 0);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_send_keysequence_window_down_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_send_keysequence_window_down_fn)input_lookup_symbol(
            "xdo_send_keysequence_window_down", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, string, delay) : -1;
}

int xdo_send_keysequence_window_up(Xdo xdo, XWindow window, const char *string,
                                   unsigned int delay) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        (void)delay;
        pthread_mutex_lock(&g_input_lock);
        send_key_name_locked(string, 0, 1);
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_send_keysequence_window_up_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_send_keysequence_window_up_fn)input_lookup_symbol(
            "xdo_send_keysequence_window_up", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, string, delay) : -1;
}

unsigned int xdo_get_input_state(Xdo xdo) {
    if (is_fake_xdo(xdo)) {
        pthread_mutex_lock(&g_input_lock);
        unsigned int mask = g_input.modifier_mask;
        pthread_mutex_unlock(&g_input_lock);
        return mask;
    }
    static real_xdo_get_input_state_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_get_input_state_fn)input_lookup_symbol(
            "xdo_get_input_state", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo) : 0;
}

int xdo_get_mouse_location(Xdo xdo, int *x, int *y, int *screen_num) {
    if (is_fake_xdo(xdo)) {
        pthread_mutex_lock(&g_input_lock);
        if (x) {
            *x = g_input.x;
        }
        if (y) {
            *y = g_input.y;
        }
        pthread_mutex_unlock(&g_input_lock);
        if (screen_num) {
            *screen_num = 0;
        }
        return 0;
    }
    static real_xdo_get_mouse_location_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_get_mouse_location_fn)input_lookup_symbol(
            "xdo_get_mouse_location", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, x, y, screen_num) : -1;
}

int xdo_get_active_window(Xdo xdo, XWindow *window) {
    if (is_fake_xdo(xdo)) {
        if (window) {
            *window = 0;
        }
        return -1;
    }
    static real_xdo_get_active_window_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_get_active_window_fn)input_lookup_symbol(
            "xdo_get_active_window", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window) : -1;
}

int xdo_get_window_location(Xdo xdo, XWindow window, int *x, int *y,
                            int *screen_num) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        if (x) {
            *x = 0;
        }
        if (y) {
            *y = 0;
        }
        if (screen_num) {
            *screen_num = 0;
        }
        return 0;
    }
    static real_xdo_get_window_location_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_get_window_location_fn)input_lookup_symbol(
            "xdo_get_window_location", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, x, y, screen_num) : -1;
}

int xdo_get_window_size(Xdo xdo, XWindow window, int *width, int *height) {
    if (is_fake_xdo(xdo)) {
        (void)window;
        pthread_mutex_lock(&g_input_lock);
        if (width) {
            *width = g_input.width;
        }
        if (height) {
            *height = g_input.height;
        }
        pthread_mutex_unlock(&g_input_lock);
        return 0;
    }
    static real_xdo_get_window_size_fn real_fn;
    if (!real_fn) {
        real_fn = (real_xdo_get_window_size_fn)input_lookup_symbol(
            "xdo_get_window_size", "libxdo.so.3");
    }
    return real_fn ? real_fn(xdo, window, width, height) : -1;
}

__attribute__((destructor)) static void rustdesk_uinput_input_cleanup(void) {
    pthread_mutex_lock(&g_input_lock);
    if (g_input.fd >= 0) {
        ioctl(g_input.fd, UI_DEV_DESTROY);
        close(g_input.fd);
        g_input.fd = -1;
    }
    if (g_xcb_mouse.connection && p_xcb_disconnect) {
        p_xcb_disconnect(g_xcb_mouse.connection);
        g_xcb_mouse.connection = NULL;
    }
    pthread_mutex_unlock(&g_input_lock);
}
