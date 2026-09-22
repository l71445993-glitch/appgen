#!/usr/bin/env python3
from pathlib import Path


ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_xdo() -> None:
    path = "libs/enigo/src/linux/xdo.rs"
    text = read(path)
    if "pub(super) fn disabled() -> Self" in text:
        print("EnigoXdo::disabled already present.")
        return
    text = replace_once(
        text,
        """impl EnigoXdo {
    /// Get the delay per keypress in microseconds.
""",
        """impl EnigoXdo {
    pub(super) fn disabled() -> Self {
        Self {
            xdo: std::ptr::null_mut(),
            delay: DEFAULT_DELAY,
        }
    }

    /// Get the delay per keypress in microseconds.
""",
        "EnigoXdo::disabled",
    )
    write(path, text)
    print("Added EnigoXdo::disabled.")


def patch_server() -> None:
    path = "src/server.rs"
    text = read(path)
    text = replace_once(
        text,
        "mod connection;\nmod login_failure_check;\npub mod display_service;\n",
        "mod connection;\npub mod display_service;\nmod login_failure_check;\n",
        "rustfmt server module ordering",
    )
    text = replace_once(text, "use scrap::camera;\n", "use scrap::{camera, Display};\n", "scrap Display import")
    text = replace_once(
        text,
        """                    let should_sync =
                        cfg != cfg0 || (is_root_config_empty && !cfg.0.is_empty());
""",
        """                    let should_sync = cfg != cfg0 || (is_root_config_empty && !cfg.0.is_empty());
""",
        "rustfmt config sync line",
    )
    text = replace_once(
        text,
        """pub async fn start_server(is_server: bool, no_server: bool) {
    use std::sync::Once;
""",
        """pub async fn start_server(is_server: bool, no_server: bool) {
    #[cfg(target_os = "linux")]
    if is_server {
        init_custom_linux_input_env();
    }

    use std::sync::Once;
""",
        "custom Linux input env init",
    )
    text = replace_once(
        text,
        """        #[cfg(target_os = "linux")]
        if input_service::wayland_use_uinput() {
            allow_err!(input_service::setup_uinput(0, 1920, 0, 1080).await);
        }
""",
        """        #[cfg(target_os = "linux")]
        if input_service::use_uinput_input() {
            let (minx, maxx, miny, maxy) = uinput_input_bounds();
            allow_err!(input_service::setup_uinput(minx, maxx, miny, maxy).await);
        }
""",
        "uinput input setup",
    )
    text = replace_once(
        text,
        """#[cfg(target_os = "macos")]
#[tokio::main(flavor = "current_thread")]
pub async fn start_ipc_url_server() {
""",
        """#[cfg(target_os = "linux")]
fn init_custom_linux_input_env() {
    if std::env::var("RUSTDESK_UINPUT_INPUT_FALLBACK").is_err() {
        std::env::set_var("RUSTDESK_UINPUT_INPUT_FALLBACK", "1");
    }
    if std::env::var("RUSTDESK_XCB_MOUSE_FALLBACK").is_err() {
        std::env::set_var("RUSTDESK_XCB_MOUSE_FALLBACK", "1");
    }
    if std::env::var("RUSTDESK_FORCE_CM_NO_UI").is_err() {
        std::env::set_var("RUSTDESK_FORCE_CM_NO_UI", "1");
    }
    if std::env::var("RUSTDESK_DISABLE_TRAY").is_err() {
        std::env::set_var("RUSTDESK_DISABLE_TRAY", "1");
    }
    if std::env::var("RUSTDESK_PREWARM_CM_NO_UI").is_err() {
        std::env::set_var("RUSTDESK_PREWARM_CM_NO_UI", "1");
    }
}

#[cfg(target_os = "linux")]
fn uinput_input_bounds() -> (i32, i32, i32, i32) {
    let displays = Display::all().unwrap_or_default();
    if displays.is_empty() {
        return (0, 1920, 0, 1080);
    }

    let mut minx = i32::MAX;
    let mut miny = i32::MAX;
    let mut maxx = i32::MIN;
    let mut maxy = i32::MIN;
    for display in displays {
        let (x, y) = display.origin();
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x + display.width() as i32);
        maxy = maxy.max(y + display.height() as i32);
    }

    if minx >= maxx || miny >= maxy {
        (0, 1920, 0, 1080)
    } else {
        (minx, maxx, miny, maxy)
    }
}

#[cfg(target_os = "macos")]
#[tokio::main(flavor = "current_thread")]
pub async fn start_ipc_url_server() {
""",
        "custom Linux helper functions",
    )
    write(path, text)
    print("Patched Linux server startup defaults.")


def patch_connection() -> None:
    path = "src/server/connection.rs"
    text = read(path)
    text = replace_once(
        text,
        """        let mut args = vec!["--cm"];
""",
        """        let mut args = if std::env::var("RUSTDESK_FORCE_CM_NO_UI").unwrap_or_default() == "1" {
            vec!["--cm-no-ui"]
        } else {
            vec!["--cm"]
        };
""",
        "CM no-ui args",
    )
    write(path, text)
    print("Patched CM no-ui startup args.")


def patch_input_service() -> None:
    path = "src/server/input_service.rs"
    text = read(path)
    text = replace_once(
        text,
        """    let mouse = super::uinput::client::UInputMouse::new().await?;
    log::info!("UInput mouse created");
""",
        """    let mouse = super::uinput::client::UInputMouse::new(minx, maxx, miny, maxy).await?;
    log::info!("UInput mouse created");
""",
        "uinput mouse bounds initialization",
    )
    text = replace_once(
        text,
        """#[cfg(target_os = "linux")]
pub async fn setup_rdp_input() -> ResultType<(), Box<dyn std::error::Error>> {
""",
        """#[cfg(target_os = "linux")]
pub fn force_uinput_input() -> bool {
    std::env::var("RUSTDESK_UINPUT_INPUT_FALLBACK")
        .map(|value| !value.is_empty() && value != "0")
        .unwrap_or(false)
}

#[cfg(target_os = "linux")]
pub fn use_uinput_input() -> bool {
    crate::is_server() && (force_uinput_input() || !crate::platform::is_x11())
}

#[cfg(target_os = "linux")]
pub async fn setup_rdp_input() -> ResultType<(), Box<dyn std::error::Error>> {
""",
        "uinput input helpers",
    )
    text = text.replace(
        "if !crate::platform::linux::is_x11() && wayland_use_uinput() {",
        "if use_uinput_input() {",
    )
    text = replace_once(
        text,
        """            if !crate::platform::linux::is_x11() {
                let mut en = ENIGO.lock().unwrap();
                if wayland_use_rdp_input() {
""",
        """            if use_uinput_input() || !crate::platform::linux::is_x11() {
                let mut en = ENIGO.lock().unwrap();
                if wayland_use_rdp_input() {
""",
        "sequence Linux input branch",
    )
    text = replace_once(
        text,
        """    std::thread::spawn(|| {
        if let Some(mouse) = ENIGO.lock().unwrap().get_custom_mouse() {
            if let Some(mouse) = mouse
                .as_mut_any()
                .downcast_mut::<super::uinput::client::UInputMouse>()
            {
                allow_err!(mouse.send_refresh());
            } else {
                log::error!("failed downcast uinput mouse");
            }
        }
    });
""",
        """    std::thread::spawn(move || {
        if let Some(mouse) = ENIGO.lock().unwrap().get_custom_mouse() {
            if let Some(mouse) = mouse
                .as_mut_any()
                .downcast_mut::<super::uinput::client::UInputMouse>()
            {
                mouse.set_resolution(minx, maxx, miny, maxy);
                allow_err!(mouse.send_refresh());
            } else {
                log::error!("failed downcast uinput mouse");
            }
        }
    });
""",
        "uinput mouse refresh bounds update",
    )
    text = replace_once(
        text,
        """                if wayland_use_uinput() {
""",
        """                if use_uinput_input() {
""",
        "sequence uinput branch",
    )
    write(path, text)
    print("Patched Linux input service fallback selection.")


def patch_uinput() -> None:
    path = "src/server/uinput.rs"
    text = read(path)
    text = replace_once(
        text,
        """    pub struct UInputMouse {
        conn: Connection,
        rt: Runtime,
    }
""",
        """    pub struct UInputMouse {
        conn: Connection,
        rt: Runtime,
        pointer: Option<super::mouce::XcbPointer>,
        x: i32,
        y: i32,
        minx: i32,
        miny: i32,
        maxx: i32,
        maxy: i32,
    }
""",
        "uinput mouse client fields",
    )
    text = replace_once(
        text,
        """    impl UInputMouse {
        pub async fn new() -> ResultType<Self> {
            let conn = ipc::connect(IPC_CONN_TIMEOUT, IPC_POSTFIX_MOUSE).await?;
            let rt = Runtime::new()?;
            Ok(Self { conn, rt })
        }
""",
        """    impl UInputMouse {
        pub async fn new(minx: i32, maxx: i32, miny: i32, maxy: i32) -> ResultType<Self> {
            let conn = ipc::connect(IPC_CONN_TIMEOUT, IPC_POSTFIX_MOUSE).await?;
            let rt = Runtime::new()?;
            Ok(Self {
                conn,
                rt,
                pointer: super::mouce::XcbPointer::new(),
                x: minx,
                y: miny,
                minx,
                miny,
                maxx,
                maxy,
            })
        }
""",
        "uinput mouse client constructor",
    )
    text = replace_once(
        text,
        """        pub fn send_refresh(&mut self) -> ResultType<()> {
            self.send(Data::Mouse(DataMouse::Refresh))
        }
    }
""",
        """        pub fn send_refresh(&mut self) -> ResultType<()> {
            self.send(Data::Mouse(DataMouse::Refresh))
        }

        pub fn set_resolution(&mut self, minx: i32, maxx: i32, miny: i32, maxy: i32) {
            self.minx = minx;
            self.maxx = maxx;
            self.miny = miny;
            self.maxy = maxy;
            let (x, y) = self.clamp_pos(self.x, self.y);
            self.x = x;
            self.y = y;
        }

        fn clamp_pos(&self, x: i32, y: i32) -> (i32, i32) {
            (
                x.clamp(self.minx, self.maxx.saturating_sub(1)),
                y.clamp(self.miny, self.maxy.saturating_sub(1)),
            )
        }

        fn move_xcb_to(&mut self, x: i32, y: i32) -> bool {
            let (x, y) = self.clamp_pos(x, y);
            self.x = x;
            self.y = y;
            let ok = match self.pointer.as_ref() {
                Some(pointer) => pointer.move_to(x, y),
                None => false,
            };
            if !ok {
                self.pointer = None;
            }
            ok
        }
    }
""",
        "uinput mouse client helpers",
    )
    text = replace_once(
        text,
        """        fn mouse_move_to(&mut self, x: i32, y: i32) {
            allow_err!(self.send(Data::Mouse(DataMouse::MoveTo(x, y))));
        }
        fn mouse_move_relative(&mut self, x: i32, y: i32) {
            allow_err!(self.send(Data::Mouse(DataMouse::MoveRelative(x, y))));
        }
""",
        """        fn mouse_move_to(&mut self, x: i32, y: i32) {
            if !self.move_xcb_to(x, y) {
                allow_err!(self.send(Data::Mouse(DataMouse::MoveTo(x, y))));
            }
        }
        fn mouse_move_relative(&mut self, x: i32, y: i32) {
            let (target_x, target_y) = self.clamp_pos(self.x + x, self.y + y);
            if !self.move_xcb_to(target_x, target_y) {
                allow_err!(self.send(Data::Mouse(DataMouse::MoveRelative(x, y))));
            }
        }
""",
        "uinput mouse client move fallback",
    )
    text = replace_once(
        text,
        """mod mouce {
    use std::{
        fs::File,
        io::{Error, ErrorKind, Result},
        mem::size_of,
        os::{
            raw::{c_char, c_int, c_long, c_uint, c_ulong, c_ushort},
            unix::{fs::OpenOptionsExt, io::AsRawFd},
        },
        thread,
        time::Duration,
    };
""",
        """mod mouce {
    use std::{
        ffi::c_void,
        fs::File,
        io::{Error, ErrorKind, Result},
        mem::size_of,
        os::{
            raw::{c_char, c_int, c_long, c_uint, c_ulong, c_ushort},
            unix::{fs::OpenOptionsExt, io::AsRawFd},
        },
        ptr, thread,
        time::Duration,
    };
""",
        "uinput mouce xcb imports",
    )
    text = replace_once(
        text,
        """    const UINPUT_MAX_NAME_SIZE: usize = 80;

    pub struct UInputMouseManager {
""",
        """    const UINPUT_MAX_NAME_SIZE: usize = 80;

    type XcbConnection = c_void;
    type XcbSetup = c_void;
    type XcbWindow = u32;

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct XcbVoidCookie {
        sequence: u32,
    }

    #[repr(C)]
    struct XcbScreenIterator {
        data: *mut XcbScreen,
        rem: c_int,
        index: c_int,
    }

    #[repr(C)]
    struct XcbScreen {
        root: XcbWindow,
        default_colormap: u32,
        white_pixel: u32,
        black_pixel: u32,
        current_input_masks: u32,
        width_in_pixels: u16,
        height_in_pixels: u16,
        width_in_millimeters: u16,
        height_in_millimeters: u16,
        min_installed_maps: u16,
        max_installed_maps: u16,
        root_visual: u32,
        backing_stores: u8,
        save_unders: u8,
        root_depth: u8,
        allowed_depths_len: u8,
    }

    #[link(name = "xcb")]
    extern "C" {
        fn xcb_connect(displayname: *const c_char, screenp: *mut c_int) -> *mut XcbConnection;
        fn xcb_disconnect(c: *mut XcbConnection);
        fn xcb_connection_has_error(c: *mut XcbConnection) -> c_int;
        fn xcb_get_setup(c: *mut XcbConnection) -> *const XcbSetup;
        fn xcb_setup_roots_iterator(r: *const XcbSetup) -> XcbScreenIterator;
        fn xcb_screen_next(i: *mut XcbScreenIterator);
        fn xcb_warp_pointer(
            c: *mut XcbConnection,
            src_window: XcbWindow,
            dst_window: XcbWindow,
            src_x: i16,
            src_y: i16,
            src_width: u16,
            src_height: u16,
            dst_x: i16,
            dst_y: i16,
        ) -> XcbVoidCookie;
        fn xcb_flush(c: *mut XcbConnection) -> c_int;
    }

    pub(super) struct XcbPointer {
        connection: *mut XcbConnection,
        root: XcbWindow,
    }

    unsafe impl Send for XcbPointer {}

    impl XcbPointer {
        pub(super) fn new() -> Option<Self> {
            if !prefer_xcb_mouse() {
                return None;
            }

            let mut screen_num = 0;
            let connection = unsafe { xcb_connect(ptr::null(), &mut screen_num) };
            if connection.is_null() {
                return None;
            }
            if unsafe { xcb_connection_has_error(connection) } != 0 {
                unsafe {
                    xcb_disconnect(connection);
                }
                return None;
            }

            let setup = unsafe { xcb_get_setup(connection) };
            if setup.is_null() {
                unsafe {
                    xcb_disconnect(connection);
                }
                return None;
            }

            let mut iter = unsafe { xcb_setup_roots_iterator(setup) };
            for _ in 0..screen_num.max(0) {
                if iter.rem <= 0 {
                    break;
                }
                unsafe {
                    xcb_screen_next(&mut iter);
                }
            }
            if iter.rem <= 0 || iter.data.is_null() {
                unsafe {
                    xcb_disconnect(connection);
                }
                return None;
            }

            let screen = unsafe { &*iter.data };
            Some(Self {
                connection,
                root: screen.root,
            })
        }

        pub(super) fn move_to(&self, x: i32, y: i32) -> bool {
            if self.connection.is_null() {
                return false;
            }

            unsafe {
                xcb_warp_pointer(
                    self.connection,
                    0,
                    self.root,
                    0,
                    0,
                    0,
                    0,
                    x.clamp(i16::MIN as i32, i16::MAX as i32) as i16,
                    y.clamp(i16::MIN as i32, i16::MAX as i32) as i16,
                );
                xcb_flush(self.connection);
                xcb_connection_has_error(self.connection) == 0
            }
        }
    }

    impl Drop for XcbPointer {
        fn drop(&mut self) {
            if !self.connection.is_null() {
                unsafe {
                    xcb_disconnect(self.connection);
                }
                self.connection = ptr::null_mut();
            }
        }
    }

    fn prefer_xcb_mouse() -> bool {
        std::env::var("RUSTDESK_XCB_MOUSE_FALLBACK")
            .map(|value| !value.is_empty() && value != "0")
            .unwrap_or(true)
    }

    pub struct UInputMouseManager {
""",
        "uinput xcb pointer helper",
    )
    write(path, text)
    print("Patched Linux uinput XCB mouse fallback.")


def main() -> None:
    patch_xdo()
    patch_server()
    patch_connection()
    patch_input_service()
    patch_uinput()


if __name__ == "__main__":
    main()
