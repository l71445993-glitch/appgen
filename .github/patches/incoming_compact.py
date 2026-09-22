from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path.cwd()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        print(f"{label} is already patched.")
        return text, False
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Could not safely patch {label}: expected 1 match, found {count}"
        )
    return text.replace(old, new, 1), True


def patch_common(width: int, height: int) -> None:
    path = ROOT / "flutter/lib/common.dart"
    text = read_text(path)
    old = """var imcomingOnlyHomeSize = Size(280, 300);\nSize getIncomingOnlyHomeSize() {\n  final magicWidth = isWindows ? 11.0 : 2.0;\n  final magicHeight = 10.0;\n  return imcomingOnlyHomeSize +\n      Offset(magicWidth, kDesktopRemoteTabBarHeight + magicHeight);\n}\n"""
    new = f"""const double kIncomingOnlyContentWidth = {width}.0;\nconst double kIncomingOnlyContentHeight = {height}.0;\nconst double kIncomingOnlyLeftPaneWidth = kIncomingOnlyContentWidth;\n\nvar imcomingOnlyHomeSize =\n    const Size(kIncomingOnlyContentWidth, kIncomingOnlyContentHeight);\n\nSize getIncomingOnlyHomeSize() {{\n  final magicWidth = isWindows ? 11.0 : 2.0;\n  final magicHeight = 10.0;\n  return imcomingOnlyHomeSize +\n      Offset(magicWidth, kDesktopRemoteTabBarHeight + magicHeight);\n}}\n"""
    text, changed = replace_once(text, old, new, "incoming home size block")
    if changed:
        write_text(path, text)


def patch_main() -> None:
    path = ROOT / "flutter/lib/main.dart"
    text = read_text(path)
    old = """  WindowOptions windowOptions = getHiddenTitleBarWindowOptions(\n      isMainWindow: true, alwaysOnTop: alwaysOnTop);\n"""
    new = """  WindowOptions windowOptions = getHiddenTitleBarWindowOptions(\n      isMainWindow: true,\n      size: bind.isIncomingOnly() ? getIncomingOnlyHomeSize() : null,\n      alwaysOnTop: alwaysOnTop);\n"""
    text, changed = replace_once(text, old, new, "main window options")
    if changed:
        write_text(path, text)


def patch_home_page() -> None:
    path = ROOT / "flutter/lib/desktop/pages/desktop_home_page.dart"
    text = read_text(path)
    old_children = """    final isIncomingOnly = bind.isIncomingOnly();\n    final isOutgoingOnly = bind.isOutgoingOnly();\n    final children = <Widget>[\n      if (!isOutgoingOnly) buildPresetPasswordWarning(),\n      if (bind.isCustomClient())\n        Align(\n          alignment: Alignment.center,\n          child: loadPowered(context),\n        ),\n      Align(\n        alignment: Alignment.center,\n        child: loadLogo(),\n      ),\n      buildTip(context),\n      if (!isOutgoingOnly) buildIDBoard(context),\n      if (!isOutgoingOnly) buildPasswordBoard(context),\n      FutureBuilder<Widget>(\n        future: Future.value(\n            Obx(() => buildHelpCards(stateGlobal.updateUrl.value))),\n        builder: (_, data) {\n          if (data.hasData) {\n            if (isIncomingOnly) {\n              if (isInHomePage()) {\n                Future.delayed(Duration(milliseconds: 300), () {\n                  _updateWindowSize();\n                });\n              }\n            }\n            return data.data!;\n          } else {\n            return const Offstage();\n          }\n        },\n      ),\n      buildPluginEntry(),\n    ];\n    if (isIncomingOnly) {\n      children.addAll([\n        Divider(),\n        OnlineStatusWidget(\n          onSvcStatusChanged: () {\n            if (isInHomePage()) {\n              Future.delayed(Duration(milliseconds: 300), () {\n                _updateWindowSize();\n              });\n            }\n          },\n        ).marginOnly(bottom: 6, right: 6)\n      ]);\n    }\n"""
    new_children = """    final isIncomingOnly = bind.isIncomingOnly();\n    final isOutgoingOnly = bind.isOutgoingOnly();\n    final children = <Widget>[\n      if (bind.isCustomClient())\n        Align(\n          alignment: Alignment.center,\n          child: loadPowered(context),\n        ),\n      Align(\n        alignment: Alignment.center,\n        child: loadLogo(),\n      ),\n      buildTip(context),\n      buildIDBoard(context),\n      buildPasswordBoard(context),\n      Divider(),\n      OnlineStatusWidget(),\n    ];\n"""
    old_width = "        width: isIncomingOnly ? 280.0 : 200.0,\n"
    new_width = "        width: isIncomingOnly ? kIncomingOnlyLeftPaneWidth : 200.0,\n"
    old_update = """  _updateWindowSize() {\n    RenderObject? renderObject = _childKey.currentContext?.findRenderObject();\n    if (renderObject == null) {\n      return;\n    }\n    if (renderObject is RenderBox) {\n      final size = renderObject.size;\n      if (size != imcomingOnlyHomeSize) {\n        imcomingOnlyHomeSize = size;\n        windowManager.setSize(getIncomingOnlyHomeSize());\n      }\n    }\n  }\n"""
    new_update = """  _updateWindowSize() {\n    windowManager.setSize(getIncomingOnlyHomeSize());\n  }\n"""
    changed = False
    text, updated = replace_once(
        text, old_children, new_children, "incoming home children block"
    )
    changed |= updated
    text, updated = replace_once(text, old_width, new_width, "incoming home width")
    changed |= updated
    text, updated = replace_once(
        text, old_update, new_update, "incoming home resize handler"
    )
    changed |= updated
    if changed:
        write_text(path, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args()
    if args.width < 180 or args.height < 220:
        raise SystemExit("Width/height are too small for the compact layout.")

    patch_common(args.width, args.height)
    patch_main()
    patch_home_page()
    print(f"Applied incoming compact layout: {args.width}x{args.height}")


if __name__ == "__main__":
    main()
