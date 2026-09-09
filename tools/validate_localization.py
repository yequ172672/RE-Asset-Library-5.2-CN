"""Validate all three add-ons' translations inside an isolated Blender 5.2.

Run with --background --factory-startup and isolated BLENDER_USER_CONFIG and
BLENDER_USER_SCRIPTS. This script never saves preferences or a blend file.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-addon", required=True, type=Path)
    parser.add_argument("--mesh-addon", required=True, type=Path)
    parser.add_argument("--chain-addon", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    paths = [args.asset_addon, args.mesh_addon, args.chain_addon]
    names = [path.resolve().name for path in paths]
    for path in paths:
        sys.path.insert(0, str(path.resolve().parent))
    view = bpy.context.preferences.view
    view.language = "zh_HANS"
    view.use_translate_interface = True
    view.use_translate_tooltips = True
    report = {"blender": bpy.app.version_string, "locale": None, "addons": {}, "checks": []}
    samples = [
        ("Operator", "Initialize RE Asset Library"),
        ("Operator", "Save Changes To Catalog"),
        ("*", "Texture Cache Path"),
        ("*", "Load Materials"),
        ("Operator", "Open Texture Cache Folder"),
        ("Operator", "Cleared texture cache."),
        ("*", "Convert to RE Engine"),
        ("Operator", "Import RE Chain"),
        ("*", "Import Unknown Hashes"),
    ]
    try:
        for cycle in range(2):
            for name in names:
                result = bpy.ops.preferences.addon_enable(module=name)
                if "FINISHED" not in result:
                    raise AssertionError(f"Failed to enable {name}: {result}")
                module = importlib.import_module(name)
                translation_module = importlib.import_module(name + ".translations")
                dictionaries = translation_module.translations_dict
                if dictionaries["zh_HANS"] != dictionaries["zh_CN"]:
                    raise AssertionError(f"Chinese locale aliases disagree: {name}")
                report["addons"][name] = {
                    "version": list(module.bl_info["version"]),
                    "messages": len({key[1] for key in dictionaries["zh_HANS"]}),
                }
                callback = getattr(module, "on_register", None)
                if callback is not None and bpy.app.timers.is_registered(callback):
                    bpy.app.timers.unregister(callback)
            view.language = "zh_HANS"
            report["locale"] = bpy.app.translations.locale
            asset_tr, mesh_tr, chain_tr = [importlib.import_module(name + ".translations") for name in names]
            assert asset_tr.tr_iface("Preview: {message}", message="READY") == "预览：READY"
            formatted = [
                asset_tr.tr_report("Installed {gameName} library.", gameName="OWOTS"),
                mesh_tr.ifacef("File Count: {count}", count=2),
                chain_tr.interface("Sub Data Count: {}", 2),
            ]
            for result, value in zip(formatted, ("OWOTS", "2", "2")):
                if value not in result or not any("\u3400" <= char <= "\u9fff" for char in result):
                    raise AssertionError(f"Dynamic translation/formatting failed: {result!r}")
            report["formatted"] = formatted
            for context, english in samples:
                chinese = bpy.app.translations.pgettext_iface(english, context)
                if not any("\u3400" <= char <= "\u9fff" for char in chinese):
                    raise AssertionError(f"Missing Chinese translation: {context!r}, {english!r}: {chinese!r}")
                report["checks"].append({"cycle": cycle, "context": context, "source": english, "translation": chinese})
            for context, english in samples:
                if bpy.app.translations.pgettext_iface(english, context) != bpy.app.translations.pgettext_tip(english, context):
                    raise AssertionError(f"Interface/tooltip translation disagrees for {english}")
            view.language = "en_US"
            for context, english in samples:
                if bpy.app.translations.pgettext_iface(english, context) != english:
                    raise AssertionError(f"English fallback failed for {english}")
            for name in reversed(names):
                result = bpy.ops.preferences.addon_disable(module=name)
                if "FINISHED" not in result:
                    raise AssertionError(f"Failed to disable {name}: {result}")
            view.language = "zh_HANS"
            for context, english in (samples[0], samples[2], samples[-2]):
                if bpy.app.translations.pgettext_iface(english, context) != english:
                    raise AssertionError(f"Translation remained after disabling all add-ons: {english}")
        report["ok"] = True
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        raise
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("LOCALIZATION_VALIDATION " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
