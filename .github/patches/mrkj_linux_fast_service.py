#!/usr/bin/env python3
from pathlib import Path


LINUX_RS = Path("src/platform/linux.rs")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {name}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if not LINUX_RS.exists():
        raise SystemExit(f"{LINUX_RS} not found; run this from the RustDesk source root")

    text = LINUX_RS.read_text(encoding="utf-8")

    old_restart = """    if !should_kill
        && !cm
        && ((*cm0 && last_restart.elapsed().as_secs() > 60)
            || last_restart.elapsed().as_secs() > 3600)
    {
"""
    new_restart = """    if !should_kill
        && !cm
        && std::env::var("RUSTDESK_FORCE_CM_NO_UI").unwrap_or_default() != "1"
        && ((*cm0 && last_restart.elapsed().as_secs() > 60)
            || last_restart.elapsed().as_secs() > 3600)
    {
"""
    text = replace_once(
        text,
        old_restart,
        new_restart,
        "disable no-ui CM restart loop",
    )

    old_get_home = """        fn get_home(&mut self) {
            self.home = "".to_string();

            let cmd = format!(
                "getent passwd '{}' | awk -F':' '{{print $6}}'",
                &self.username
            );
            self.home = run_cmds_trim_newline(&cmd).unwrap_or(format!("/home/{}", &self.username));
        }
"""
    fast_x11_method = """        fn get_home(&mut self) {
            self.home = "".to_string();

            let cmd = format!(
                "getent passwd '{}' | awk -F':' '{{print $6}}'",
                &self.username
            );
            self.home = run_cmds_trim_newline(&cmd).unwrap_or(format!("/home/{}", &self.username));
        }

        fn apply_fast_x11_defaults(&mut self) -> bool {
            if self.protocol != DISPLAY_SERVER_X11
                || self.sid.is_empty()
                || self.username.is_empty()
                || self.uid.is_empty()
            {
                return false;
            }

            if self.home.is_empty() {
                self.get_home();
            }

            if self.display.is_empty() {
                self.display = run_cmds_trim_newline(&format!(
                    "loginctl show-session '{}' -p Display --value",
                    self.sid
                ))
                .unwrap_or_default();
                if self.display.is_empty() {
                    self.display = Self::get_display_by_user(&self.username);
                }
                if self.display.is_empty() && std::path::Path::new("/tmp/.X11-unix/X0").exists() {
                    self.display = ":0".to_owned();
                }
            }
            self.display = self
                .display
                .replace(&hbb_common::whoami::hostname(), "")
                .replace("localhost", "");

            if self.xauth.is_empty() && !self.home.is_empty() {
                let xauth = format!("{}/.Xauthority", self.home);
                if std::path::Path::new(&xauth).exists() {
                    self.xauth = xauth;
                }
            }

            !self.display.is_empty() && !self.xauth.is_empty()
        }
"""
    text = replace_once(
        text,
        old_get_home,
        fast_x11_method,
        "add fast X11 desktop env detection",
    )

    old_active_refresh = """            if !self.sid.is_empty() && is_active_and_seat0(&self.sid) {
                // Xwayland display and xauth may not be available in a short time after login.
                if is_xwayland_running() && !self.is_login_wayland() {
                    self.get_display_xauth_xwayland();
                    self.is_rustdesk_subprocess = false;
                }
                return;
            }
"""
    old_active_refresh_147 = """            if !self.sid.is_empty() && is_active_and_seat0(&self.sid) {
                // Xwayland display and xauth may not be available in a short time after login.
                if is_xwayland_running() && !self.is_login_wayland() {
                    self.get_display_xauth_xwayland();
                    self.is_rustdesk_subprocess = false;
                } else if self.is_wayland() {
                    self.get_display_xauth_wayland();
                }
                return;
            }
"""
    new_active_refresh = """            if !self.sid.is_empty() && is_active_and_seat0(&self.sid) {
                if self.protocol == DISPLAY_SERVER_X11
                    && (self.display.is_empty() || self.xauth.is_empty())
                    && self.apply_fast_x11_defaults()
                {
                    self.set_is_subprocess();
                } else if is_xwayland_running() && !self.is_login_wayland() {
                    // Xwayland display and xauth may not be available in a short time after login.
                    self.get_display_xauth_xwayland();
                    self.is_rustdesk_subprocess = false;
                } else if self.is_wayland() {
                    self.get_display_xauth_wayland();
                }
                return;
            }
"""
    if new_active_refresh not in text:
        if old_active_refresh_147 in text:
            text = text.replace(old_active_refresh_147, new_active_refresh, 1)
        else:
            text = replace_once(
                text,
                old_active_refresh,
                new_active_refresh,
                "use fast X11 env on active session refresh",
            )

    old_x11_branch = """            } else {
                self.get_display_x11();
                self.get_xauth_x11();
                self.set_is_subprocess();
            }
"""
    new_x11_branch = """            } else if self.apply_fast_x11_defaults() {
                self.set_is_subprocess();
            } else {
                self.get_display_x11();
                self.get_xauth_x11();
                self.set_is_subprocess();
            }
"""
    text = replace_once(
        text,
        old_x11_branch,
        new_x11_branch,
        "prefer fast X11 env before slow process scan",
    )

    LINUX_RS.write_text(text, encoding="utf-8")
    print("Applied MRKJ Linux fast service patch")


if __name__ == "__main__":
    main()
