#!/usr/bin/env python3
from pathlib import Path


NIX_IMPL = Path("libs/enigo/src/linux/nix_impl.rs")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {name}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if not NIX_IMPL.exists():
        raise SystemExit(f"{NIX_IMPL} not found; run this from the RustDesk source root")

    text = NIX_IMPL.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """    custom_keyboard: Option<CustomKeyboard>,
    custom_mouse: Option<CustomMouce>,
}
""",
        """    custom_keyboard: Option<CustomKeyboard>,
    custom_mouse: Option<CustomMouce>,
    prefer_custom_keyboard: bool,
}
""",
        "add separate custom keyboard flag",
    )

    text = replace_once(
        text,
        """    fn default() -> Self {
        let prefer_custom = prefer_custom_input();
        let is_x11 = hbb_common::platform::linux::is_x11_or_headless() && !prefer_custom;
        Self {
            is_x11,
            tfc: if is_x11 {
                match TFC_Context::new() {
                    Ok(ctx) => Some(ctx),
                    Err(..) => {
                        println!("kbd context error");
                        None
                    }
                }
            } else {
                None
            },
            custom_keyboard: None,
            custom_mouse: None,
            xdo: if prefer_custom {
                EnigoXdo::disabled()
            } else {
                EnigoXdo::default()
            },
        }
    }
""",
        """    fn default() -> Self {
        let prefer_custom_keyboard = prefer_custom_input();
        let is_x11 = hbb_common::platform::linux::is_x11_or_headless();
        Self {
            is_x11,
            tfc: if is_x11 && !prefer_custom_keyboard {
                match TFC_Context::new() {
                    Ok(ctx) => Some(ctx),
                    Err(..) => {
                        println!("kbd context error");
                        None
                    }
                }
            } else {
                None
            },
            custom_keyboard: None,
            custom_mouse: None,
            xdo: if is_x11 {
                EnigoXdo::default()
            } else {
                EnigoXdo::disabled()
            },
            prefer_custom_keyboard,
        }
    }
""",
        "keep X11 mouse while forcing custom keyboard",
    )

    text = replace_once(
        text,
        """    fn get_key_state(&mut self, key: Key) -> bool {
        if self.is_x11 {
            self.xdo.get_key_state(key)
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.get_key_state(key)
            } else {
                get_led_state(key)
            }
        }
    }
""",
        """    fn get_key_state(&mut self, key: Key) -> bool {
        if self.prefer_custom_keyboard {
            if let Some(keyboard) = &mut self.custom_keyboard {
                return keyboard.get_key_state(key);
            }
        }
        if self.is_x11 {
            self.xdo.get_key_state(key)
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.get_key_state(key)
            } else {
                get_led_state(key)
            }
        }
    }
""",
        "prefer custom get_key_state",
    )

    text = replace_once(
        text,
        """    fn key_sequence(&mut self, sequence: &str) {
        if self.is_x11 {
            self.xdo.key_sequence(sequence)
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_sequence(sequence)
            } else {
                log::warn!("Enigo::key_sequence: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        """    fn key_sequence(&mut self, sequence: &str) {
        if self.prefer_custom_keyboard {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_sequence(sequence);
                return;
            }
        }
        if self.is_x11 {
            self.xdo.key_sequence(sequence)
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_sequence(sequence)
            } else {
                log::warn!("Enigo::key_sequence: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        "prefer custom key_sequence",
    )

    text = replace_once(
        text,
        """    fn key_down(&mut self, key: Key) -> crate::ResultType {
        if self.is_x11 {
            let has_down = self.tfc_key_down_or_up(key, true, false);
            if !has_down {
                self.xdo.key_down(key)
            } else {
                Ok(())
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_down(key)
            } else {
                log::warn!("Enigo::key_down: no custom_keyboard set for Wayland!");
                Ok(())
            }
        }
    }
""",
        """    fn key_down(&mut self, key: Key) -> crate::ResultType {
        if self.prefer_custom_keyboard {
            if let Some(keyboard) = &mut self.custom_keyboard {
                return keyboard.key_down(key);
            }
        }
        if self.is_x11 {
            let has_down = self.tfc_key_down_or_up(key, true, false);
            if !has_down {
                self.xdo.key_down(key)
            } else {
                Ok(())
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_down(key)
            } else {
                log::warn!("Enigo::key_down: no custom_keyboard set for Wayland!");
                Ok(())
            }
        }
    }
""",
        "prefer custom key_down",
    )

    text = replace_once(
        text,
        """    fn key_up(&mut self, key: Key) {
        if self.is_x11 {
            let has_down = self.tfc_key_down_or_up(key, false, true);
            if !has_down {
                self.xdo.key_up(key)
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_up(key)
            } else {
                log::warn!("Enigo::key_up: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        """    fn key_up(&mut self, key: Key) {
        if self.prefer_custom_keyboard {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_up(key);
                return;
            }
        }
        if self.is_x11 {
            let has_down = self.tfc_key_down_or_up(key, false, true);
            if !has_down {
                self.xdo.key_up(key)
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_up(key)
            } else {
                log::warn!("Enigo::key_up: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        "prefer custom key_up",
    )

    text = replace_once(
        text,
        """    fn key_click(&mut self, key: Key) {
        if self.is_x11 {
            // X11: try tfc first, then fallback to key_down/key_up
            if self.tfc_key_click(key).is_err() {
                self.key_down(key).ok();
                self.key_up(key);
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_click(key);
            } else {
                log::warn!("Enigo::key_click: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        """    fn key_click(&mut self, key: Key) {
        if self.prefer_custom_keyboard {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_click(key);
                return;
            }
        }
        if self.is_x11 {
            // X11: try tfc first, then fallback to key_down/key_up
            if self.tfc_key_click(key).is_err() {
                self.key_down(key).ok();
                self.key_up(key);
            }
        } else {
            if let Some(keyboard) = &mut self.custom_keyboard {
                keyboard.key_click(key);
            } else {
                log::warn!("Enigo::key_click: no custom_keyboard set for Wayland!");
            }
        }
    }
""",
        "prefer custom key_click",
    )

    NIX_IMPL.write_text(text, encoding="utf-8")
    print("Applied MRKJ Linux X11 mouse + uinput keyboard patch")


if __name__ == "__main__":
    main()
