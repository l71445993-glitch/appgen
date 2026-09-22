from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()
NATIVE_MODEL = ROOT / "flutter/lib/models/native_model.dart"
MAIN_SERVICE = ROOT / (
    "flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainService.kt"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"{label} is already patched.")
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Unable to patch {label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_flutter_main_process() -> None:
    text = NATIVE_MODEL.read_text(encoding="utf-8")
    old = """      await _ffiBind.mainInit(
        appDir: _dir,
        customClientConfig: '',
      );
"""
    new = """      var customClientConfig = '';
      try {
        customClientConfig =
            (await rootBundle.loadString('assets/custom_.txt')).trim();
      } catch (e) {
        debugPrint('Embedded custom client config is unavailable: $e');
      }
      await _ffiBind.mainInit(
        appDir: _dir,
        customClientConfig: customClientConfig,
      );
"""
    text = replace_once(text, old, new, "Android Flutter custom config loader")
    NATIVE_MODEL.write_text(text, encoding="utf-8")


def patch_android_service_process() -> None:
    text = MAIN_SERVICE.read_text(encoding="utf-8")
    old = """        val configPath = prefs.getString(KEY_APP_DIR_CONFIG_PATH, "") ?: ""
        FFI.startServer(configPath, "")
"""
    new = """        val configPath = prefs.getString(KEY_APP_DIR_CONFIG_PATH, "") ?: ""
        val customClientConfig = try {
            assets.open("flutter_assets/assets/custom_.txt")
                .bufferedReader()
                .use { it.readText().trim() }
        } catch (e: Exception) {
            Log.w(logTag, "Embedded custom client config is unavailable", e)
            ""
        }
        FFI.startServer(configPath, customClientConfig)
"""
    text = replace_once(text, old, new, "Android service custom config loader")
    MAIN_SERVICE.write_text(text, encoding="utf-8")


def main() -> None:
    if not NATIVE_MODEL.is_file() or not MAIN_SERVICE.is_file():
        raise SystemExit("Android RustDesk source files are missing")
    patch_flutter_main_process()
    patch_android_service_process()
    print("Enabled embedded custom config in Android UI and service processes.")


if __name__ == "__main__":
    main()
