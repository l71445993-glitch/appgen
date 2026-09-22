from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            print(f"{label} already patched.")
            return text
        raise SystemExit(f"Could not find {label}")
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, new: str, label: str) -> str:
    start_index = text.find(start)
    if start_index == -1:
        if new in text:
            print(f"{label} already patched.")
            return text
        raise SystemExit(f"Could not find start of {label}")
    end_index = text.find(end, start_index)
    if end_index == -1:
        raise SystemExit(f"Could not find end of {label}")
    return text[:start_index] + new + text[end_index:]


def patch_peer_tab_model() -> None:
    path = ROOT / "flutter/lib/models/peer_tab_model.dart"
    text = read_text(path)
    old = """  List<bool> isEnabled = List.from([
    true,
    true,
    !isWeb && bind.mainGetLocalOption(key: "disable-discovery-panel") != "Y",
    !(bind.isDisableAb() || bind.isDisableAccount()),
    !(bind.isDisableGroupPanel() || bind.isDisableAccount()),
  ]);
"""
    new = """  List<bool> isEnabled = List.from([
    false,
    true,
    !isWeb && bind.mainGetLocalOption(key: "disable-discovery-panel") != "Y",
    !(bind.isDisableAb() || bind.isDisableAccount()),
    !(bind.isDisableGroupPanel() || bind.isDisableAccount()),
  ]);
"""
    text = replace_once(text, old, new, "recent tab visibility")
    text = replace_once(
        text,
        """  setCurrentTab(int index) {
    if (_currentTab != index) {
      _currentTab = index;
      notifyListeners();
    }
  }
""",
        """  setCurrentTab(int index) {
    if (index < 0 ||
        index >= maxTabCount ||
        !visibleEnabledOrderedIndexs.contains(index)) {
      _trySetCurrentTabToFirstVisibleEnabled();
      return;
    }
    if (_currentTab != index) {
      _currentTab = index;
      notifyListeners();
    }
  }
""",
        "disabled recent tab selection guard",
    )
    write_text(path, text)


def patch_peer_tab_page() -> None:
    path = ROOT / "flutter/lib/common/widgets/peer_tab_page.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """    _TabEntry(RecentPeersView(
      menuPadding: _menuPadding(),
    )),
""",
        """    _TabEntry(const SizedBox.shrink()),
""",
        "recent tab widget entry",
    )
    text = replace_once(
        text,
        """  Future<void> handleTabSelection(int tabIndex) async {
    if (tabIndex < entries.length) {
      if (tabIndex != gFFI.peerTabModel.currentTab) {
        gFFI.peerTabModel.setCurrentTabCachedPeers([]);
      }
      gFFI.peerTabModel.setCurrentTab(tabIndex);
      entries[tabIndex].load?.call(hint: false);
    }
  }
""",
        """  Future<void> handleTabSelection(int tabIndex) async {
    if (tabIndex < 0 ||
        tabIndex >= entries.length ||
        !gFFI.peerTabModel.visibleEnabledOrderedIndexs.contains(tabIndex)) {
      return;
    }
    if (tabIndex != gFFI.peerTabModel.currentTab) {
      gFFI.peerTabModel.setCurrentTabCachedPeers([]);
    }
    gFFI.peerTabModel.setCurrentTab(tabIndex);
    entries[tabIndex].load?.call(hint: false);
  }
""",
        "disabled recent tab tap guard",
    )
    text = replace_once(
        text,
        """        child = entries[0].widget;
""",
        """        child = entries[model.visibleEnabledOrderedIndexs[0]].widget;
""",
        "recent tab fallback view",
    )
    text = replace_once(
        text,
        """              case 0:
                for (var p in peers) {
                  await bind.mainRemovePeer(id: p.id);
                }
                bind.mainLoadRecentPeers();
                break;
""",
        """              case 0:
                break;
""",
        "recent tab delete action",
    )
    write_text(path, text)


def patch_flutter_bridge() -> None:
    path = ROOT / "flutter/lib/web/bridge.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """  Future<void> mainLoadRecentPeers({dynamic hint}) {
    return Future(
        () => js.context.callMethod('getByName', ['load_recent_peers']));
  }
""",
        """  Future<void> mainLoadRecentPeers({dynamic hint}) {
    return Future.value();
  }
""",
        "web recent peers async loader",
    )
    text = replace_once(
        text,
        """  String mainLoadRecentPeersSync({dynamic hint}) {
    return js.context.callMethod('getByName', ['load_recent_peers_sync']);
  }
""",
        """  String mainLoadRecentPeersSync({dynamic hint}) {
    return '';
  }
""",
        "web recent peers sync loader",
    )
    text = replace_once(
        text,
        """  Future<String> mainLoadRecentPeersForAb(
      {required String filter, dynamic hint}) {
    throw UnimplementedError("mainLoadRecentPeersForAb");
  }
""",
        """  Future<String> mainLoadRecentPeersForAb(
      {required String filter, dynamic hint}) {
    return Future.value('');
  }
""",
        "web recent peers address-book loader",
    )
    write_text(path, text)


def patch_flutter_recent_callers() -> None:
    path = ROOT / "flutter/lib/common/widgets/peers_view.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """    final widget = super.build(context);
    bind.mainLoadRecentPeers();
    return widget;
""",
        """    return super.build(context);
""",
        "recent peers view loader",
    )
    write_text(path, text)

    path = ROOT / "flutter/lib/common/widgets/autocomplete.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """    gFFI.recentPeersModel.addListener(_mergeAllPeers);
    gFFI.lanPeersModel.addListener(_mergeAllPeers);
""",
        """    gFFI.lanPeersModel.addListener(_mergeAllPeers);
""",
        "autocomplete recent listener",
    )
    text = replace_once(
        text,
        """    gFFI.recentPeersModel.removeListener(_mergeAllPeers);
    gFFI.lanPeersModel.removeListener(_mergeAllPeers);
""",
        """    gFFI.lanPeersModel.removeListener(_mergeAllPeers);
""",
        "autocomplete recent listener cleanup",
    )
    text = replace_once(
        text,
        """    if (gFFI.recentPeersModel.peers.isEmpty) {
      bind.mainLoadRecentPeers();
    }
    if (gFFI.lanPeersModel.peers.isEmpty) {
""",
        """    if (gFFI.lanPeersModel.peers.isEmpty) {
""",
        "autocomplete recent load",
    )
    text = replace_once(
        text,
        """
    for (final peer in gFFI.recentPeersModel.peers) {
      if (!peerIds.contains(peer.id)) {
        parsedPeers.add(peer);
        peerIds.add(peer.id);
      }
    }
    for (final id in gFFI.recentPeersModel.restPeerIds) {
      if (!peerIds.contains(id)) {
        parsedPeers.add(Peer.fromJson({'id': id}));
        peerIds.add(id);
      }
    }
""",
        "\n",
        "autocomplete recent merge",
    )
    write_text(path, text)

    path = ROOT / "flutter/lib/models/model.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """
    // Recent peer is updated by handle_peer_info(ui_session_interface.rs) --> handle_peer_info(client.rs) --> save_config(client.rs)
    bind.mainLoadRecentPeers();
""",
        "\n",
        "session recent peer refresh",
    )
    write_text(path, text)

    path = ROOT / "flutter/lib/common/widgets/peer_card.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """            case PeerTabIndex.recent:
              await bind.mainRemovePeer(id: id);
              bind.mainLoadRecentPeers();
              break;
""",
        """            case PeerTabIndex.recent:
              break;
""",
        "recent peer card remove action",
    )
    text = replace_once(
        text,
        """  void _update() => bind.mainLoadRecentPeers();
""",
        """  void _update() {}
""",
        "recent peer card refresh",
    )
    write_text(path, text)


def patch_address_book_recent_sync() -> None:
    path = ROOT / "flutter/lib/models/ab_model.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """bool shouldSyncAb() {
  return bind.mainGetLocalOption(key: syncAbOption) == 'Y';
}
""",
        """bool shouldSyncAb() {
  return false;
}
""",
        "address-book recent sync option",
    )
    write_text(path, text)

    path = ROOT / "flutter/lib/common/widgets/address_book.dart"
    text = read_text(path)
    text = replace_once(
        text,
        """      if (canWrite) syncMenuItem(),
""",
        "",
        "address-book recent sync menu",
    )
    write_text(path, text)


def patch_flutter_ffi() -> None:
    path = ROOT / "src/flutter_ffi.rs"
    text = read_text(path)
    text = replace_block(
        text,
        "pub fn main_get_new_stored_peers() -> String {",
        "\npub fn main_forget_password",
        """pub fn main_get_new_stored_peers() -> String {
    String::new()
}

""",
        "new stored peers drain",
    )
    text = replace_block(
        text,
        "pub fn main_load_recent_peers() {",
        "\npub fn main_load_recent_peers_for_ab",
        """pub fn main_load_recent_peers() {
    let data = HashMap::from([
        ("name", "load_recent_peers".to_owned()),
        ("peers", String::new()),
    ]);
    let _res = flutter::push_global_event(
        flutter::APP_TYPE_MAIN,
        serde_json::ser::to_string(&data).unwrap_or("".to_owned()),
    );
}

""",
        "native recent peers loader",
    )
    text = replace_block(
        text,
        "pub fn main_load_recent_peers_for_ab",
        "\npub fn main_load_fav_peers()",
        """pub fn main_load_recent_peers_for_ab(_filter: String) -> String {
    String::new()
}
""",
        "native recent peers address-book loader",
    )
    write_text(path, text)


def patch_recent_writes() -> None:
    path = ROOT / "src/client.rs"
    text = read_text(path)
    text = replace_once(
        text,
        """    pub fn load_config(&self) -> PeerConfig {
        debug_assert!(self.id.len() > 0);
        PeerConfig::load(&self.id)
    }
""",
        """    pub fn load_config(&self) -> PeerConfig {
        debug_assert!(self.id.len() > 0);
        self.config.clone()
    }
""",
        "peer config disk load",
    )
    text = replace_once(
        text,
        """    pub fn save_config(&mut self, config: PeerConfig) {
        config.store(&self.id);
        self.config = config;
    }
""",
        """    pub fn save_config(&mut self, config: PeerConfig) {
        self.config = config;
    }
""",
        "peer config disk store",
    )
    text = replace_once(
        text,
        """                log::debug!("remember password of {}", self.id);
""",
        "",
        "remember-password recent debug log",
    )
    text = replace_once(
        text,
        """                log::debug!("save ab password of {} to recent", self.id);
""",
        "",
        "address-book password recent debug log",
    )
    text = replace_once(
        text,
        """                log::debug!("remove password of {}", self.id);
""",
        "",
        "remove-password recent debug log",
    )
    text = replace_once(
        text,
        """    pub fn set_direct_failure(&mut self, value: i32) {
        let mut config = self.load_config();
        config.direct_failures = value;
        self.save_config(config);
    }
""",
        """    pub fn set_direct_failure(&mut self, value: i32) {
        self.config.direct_failures = value;
    }
""",
        "direct-failure recent-session store",
    )
    text = replace_once(
        text,
        """            self.config.store(&self.id);
            return None;
""",
        """            return None;
""",
        "direct peer option store",
    )
    text = replace_once(
        text,
        """        // no matter if change, for update file time
        self.save_config(config);
        self.supported_encoding = pi.encoding.clone().unwrap_or_default();
""",
        """        // Keep peer info in memory only; do not create/update recent-session records.
        self.config = config;
        self.supported_encoding = pi.encoding.clone().unwrap_or_default();
""",
        "peer info recent-session store",
    )
    write_text(path, text)

    path = ROOT / "src/ui_session_interface.rs"
    text = read_text(path)
    text = replace_once(
        text,
        """        log::debug!("handle_peer_info :{:?}", pi);
""",
        "",
        "peer-info recent debug log",
    )
    text = replace_once(
        text,
        """        // Save recent peers, then push event to flutter. So flutter can refresh peer page.
        self.lc.write().unwrap().handle_peer_info(&pi);
""",
        """        // Keep peer info in memory only; do not create or refresh recent-session records.
        self.lc.write().unwrap().handle_peer_info(&pi);
""",
        "recent peer save comment",
    )
    text = replace_once(
        text,
        """        #[cfg(windows)]
        {
            let mut path = std::env::temp_dir();
            path.push(self.get_id());
            let path = path.with_extension(crate::get_app_name().to_lowercase());
            std::fs::File::create(&path).ok();
            if let Some(path) = path.to_str() {
                crate::platform::windows::add_recent_document(&path);
            }
        }
""",
        """        // Windows recent document registration is disabled with recent sessions.
""",
        "Windows recent document registration",
    )
    write_text(path, text)

    path = ROOT / "src/ui_interface.rs"
    text = read_text(path)
    text = replace_once(
        text,
        """pub fn forget_password(id: String) {
    let mut c = PeerConfig::load(&id);
    c.password.clear();
    c.store(&id);
}
""",
        """pub fn forget_password(id: String) {
    let mut c = PeerConfig::load(&id);
    c.password.clear();
}
""",
        "forget password recent store",
    )
    text = replace_once(
        text,
        """#[cfg(feature = "flutter")]
pub fn set_peer_flutter_option(id: String, name: String, value: String) {
    let mut c = PeerConfig::load(&id);
    if value.is_empty() {
        c.ui_flutter.remove(&name);
    } else {
        c.ui_flutter.insert(name, value);
    }
    c.store(&id);
}
""",
        """#[cfg(feature = "flutter")]
pub fn set_peer_flutter_option(_id: String, _name: String, _value: String) {}
""",
        "peer flutter option recent store",
    )
    text = replace_once(
        text,
        """pub fn set_peer_option(id: String, name: String, value: String) {
    let mut c = PeerConfig::load(&id);
    if value.is_empty() {
        c.options.remove(&name);
    } else {
        c.options.insert(name, value);
    }
    c.store(&id);
}
""",
        """pub fn set_peer_option(_id: String, _name: String, _value: String) {}
""",
        "peer option recent store",
    )
    write_text(path, text)


def patch_legacy_ui() -> None:
    path = ROOT / "src/ui.rs"
    text = read_text(path)
    text = replace_once(
        text,
        """    fn get_recent_sessions(&mut self) -> Value {
        // to-do: limit number of recent sessions, and remove old peer file
        let peers: Vec<Value> = PeerConfig::peers(None)
            .drain(..)
            .map(|p| Self::get_peer_value(p.0, p.2))
            .collect();
        Value::from_iter(peers)
    }
""",
        """    fn get_recent_sessions(&mut self) -> Value {
        Value::from_iter(Vec::<Value>::new())
    }
""",
        "legacy recent sessions list",
    )
    write_text(path, text)

    path = ROOT / "src/ui_interface.rs"
    text = read_text(path)
    text = replace_once(
        text,
        """pub fn recent_sessions_updated() -> bool {
    let mut children = CHILDREN.lock().unwrap();
    if children.0 {
        children.0 = false;
        true
    } else {
        false
    }
}
""",
        """pub fn recent_sessions_updated() -> bool {
    false
}
""",
        "legacy recent sessions update flag",
    )
    write_text(path, text)

    path = ROOT / "src/ui/ab.tis"
    text = read_text(path)
    text = replace_once(
        text,
        """function getSessionsType() {
    return handler.get_local_option("show-sessions-type");
}
""",
        """function getSessionsType() {
    var type = handler.get_local_option("show-sessions-type");
    return type ? type : "fav";
}
""",
        "legacy sessions default tab",
    )
    text = replace_once(
        text,
        """                        <span class={!type ? 'active' : 'inactive'}>{translate('Recent sessions')}</span>
""",
        "",
        "legacy recent sessions tab",
    )
    write_text(path, text)


def main() -> None:
    patch_peer_tab_model()
    patch_peer_tab_page()
    patch_flutter_bridge()
    patch_flutter_recent_callers()
    patch_address_book_recent_sync()
    patch_flutter_ffi()
    patch_recent_writes()
    patch_legacy_ui()
    print("Removed recent sessions UI and disabled recent-session recording.")


if __name__ == "__main__":
    main()
